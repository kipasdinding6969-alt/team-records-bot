"""Report generation engine for various report types."""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta
import json

from database import database
from models import DailySummaryRecord, TeamWeeklyRecord, ReportTemplate
from utils.formatting import (
    format_currency, format_percentage, format_date_chinese,
    format_table_row, format_report_header
)

logger = logging.getLogger(__name__)


class ReportEngine:
    """Central report generation engine."""

    def __init__(self):
        self.template_registry = {
            'daily_summary': self.generate_daily_summary_report,
            'weekly_assessment': self.generate_weekly_assessment_report,
            'performance_analysis': self.generate_performance_analysis_report,
            'financial_overview': self.generate_financial_overview_report,
            'client_status': self.generate_client_status_report
        }

    async def generate_report(self, template: ReportTemplate) -> Dict[str, Any]:
        """Generate report based on template."""
        try:
            generator = self.template_registry.get(template.template_type)
            if not generator:
                raise ValueError(f"Unknown report template: {template.template_type}")

            report_data = await generator(template)

            # Add metadata
            report_data['metadata'] = {
                'template_type': template.template_type,
                'generated_at': datetime.now().isoformat(),
                'parameters': template.parameters
            }

            logger.info(f"Generated report: {template.template_type}")
            return report_data

        except Exception as e:
            logger.error(f"Failed to generate report {template.template_type}: {e}")
            raise

    async def generate_daily_summary_report(self, template: ReportTemplate) -> Dict[str, Any]:
        """Generate Type 4: Daily Summary Report."""
        target_date = template.parameters.get('date', date.today())
        if isinstance(target_date, str):
            target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

        date_str = target_date.strftime("%m月%d日")

        # Get all active frontdesk members
        async with database.get_connection() as db:
            cursor = await db.execute("""
                SELECT frontdesk_name FROM team_members
                WHERE role = 'frontdesk' AND is_active = TRUE AND frontdesk_name IS NOT NULL
            """)
            frontdesk_members = [row[0] for row in await cursor.fetchall()]

        sections = {
            'today_stats': {},      # Section A
            'cumulative_totals': {}, # Section B
            'today_training_details': {}, # Section C
            'total_training_details': {}  # Section D
        }

        totals = {
            'today_stats': {'new_powder': 0, 'today_reply': 0, 'today_register': 0,
                           'today_completed_training': 0, 'today_withdraw': 0, 'today_new_order': 0},
            'cumulative_totals': {'total_powder': 0, 'total_reply': 0, 'total_register': 0,
                                 'total_completed_training': 0, 'total_withdraw': 0, 'total_new_order': 0},
            'today_training_details': {'today_training': 0, 'today_withdraw': 0, 'today_not_withdraw': 0,
                                      'today_training_and_withdraw': 0, 'today_conversion': 0},
            'total_training_details': {'total_training': 0, 'total_withdraw': 0, 'total_not_withdraw': 0,
                                      'total_training_and_withdraw': 0, 'total_conversion': 0}
        }

        for frontdesk in frontdesk_members:
            # Get all client records for this frontdesk
            records = await database.get_client_records_by_frontdesk(frontdesk)
            today_records = [r for r in records if r.date == date_str]

            # Section A: Today's Stats
            today_stats = {
                'frontdesk': frontdesk,
                'new_powder': len(today_records),
                'today_reply': len([r for r in today_records if r.first_day != '待定']),
                'today_register': len([r for r in today_records if r.first_day == '注册']),
                'today_completed_training': len([r for r in today_records if r.second_day == '注册']),
                'today_withdraw': await self._get_financial_metric(frontdesk, date_str, 'withdraw'),
                'today_new_order': await self._get_financial_metric(frontdesk, date_str, 'new_order')
            }
            sections['today_stats'][frontdesk] = today_stats

            # Section B: Cumulative Totals
            cumulative_stats = {
                'frontdesk': frontdesk,
                'total_powder': len(records),
                'total_reply': len([r for r in records if r.first_day != '待定']),
                'total_register': len([r for r in records if r.first_day == '注册']),
                'total_completed_training': len([r for r in records if r.second_day == '注册']),
                'total_withdraw': await self._get_financial_metric(frontdesk, None, 'withdraw', cumulative=True),
                'total_new_order': await self._get_financial_metric(frontdesk, None, 'new_order', cumulative=True)
            }
            sections['cumulative_totals'][frontdesk] = cumulative_stats

            # Section C: Today's Training Details
            training_today = len([r for r in today_records if r.second_day == '注册'])
            today_training_details = {
                'frontdesk': frontdesk,
                'today_training': training_today,
                'today_withdraw': today_stats['today_withdraw'],
                'today_not_withdraw': max(0, training_today - today_stats['today_withdraw']),
                'today_training_and_withdraw': min(training_today, today_stats['today_withdraw']),
                'today_conversion': today_stats['today_new_order']
            }
            sections['today_training_details'][frontdesk] = today_training_details

            # Section D: Total Training Details
            training_total = len([r for r in records if r.second_day == '注册'])
            total_training_details = {
                'frontdesk': frontdesk,
                'total_training': training_total,
                'total_withdraw': cumulative_stats['total_withdraw'],
                'total_not_withdraw': max(0, training_total - cumulative_stats['total_withdraw']),
                'total_training_and_withdraw': min(training_total, cumulative_stats['total_withdraw']),
                'total_conversion': cumulative_stats['total_new_order']
            }
            sections['total_training_details'][frontdesk] = total_training_details

            # Add to totals
            for section_name, section_data in sections.items():
                if frontdesk in section_data:
                    for key, value in section_data[frontdesk].items():
                        if key != 'frontdesk' and key in totals[section_name]:
                            totals[section_name][key] += value or 0

        return {
            'report_type': 'daily_summary',
            'date': target_date,
            'date_chinese': date_str,
            'sections': sections,
            'totals': totals,
            'frontdesk_count': len(frontdesk_members),
            'formatted_report': self._format_daily_summary_report(sections, totals, target_date)
        }

    async def _get_financial_metric(self, frontdesk: str, date_str: Optional[str],
                                   metric: str, cumulative: bool = False) -> int:
        """Get financial metric for frontdesk member."""
        try:
            if cumulative:
                records = await database.get_financial_records_by_date("", "")  # All records
            else:
                records = await database.get_financial_records_by_date(date_str) if date_str else []

            frontdesk_records = [r for r in records if r.frontdesk == frontdesk]

            if metric == 'withdraw':
                # Count withdrawal records (simplified)
                return len([r for r in frontdesk_records if r.note and '提款' in r.note])
            elif metric == 'new_order':
                # Count new order records
                return len([r for r in frontdesk_records if r.new_order_amount and r.new_order_amount > 0])

            return 0
        except Exception as e:
            logger.warning(f"Failed to get financial metric {metric} for {frontdesk}: {e}")
            return 0

    def _format_daily_summary_report(self, sections: Dict, totals: Dict, target_date: date) -> str:
        """Format daily summary report for display."""
        report = f"""
📊 **日报 / Daily Summary Report**
📅 **日期 / Date:** {target_date.strftime('%Y-%m-%d')} ({target_date.strftime('%m月%d日')})

**📈 Section A: 今日统计 / Today's Stats**
"""

        # Table header
        report += "```\n"
        report += f"{'前台':<8} {'新粉':<6} {'回复':<6} {'注册':<6} {'培训':<6} {'提款':<6} {'新单':<6}\n"
        report += "-" * 50 + "\n"

        for frontdesk, stats in sections['today_stats'].items():
            report += f"{frontdesk:<8} {stats['new_powder']:<6} {stats['today_reply']:<6} " \
                     f"{stats['today_register']:<6} {stats['today_completed_training']:<6} " \
                     f"{stats['today_withdraw']:<6} {stats['today_new_order']:<6}\n"

        # Add totals row
        t = totals['today_stats']
        report += "-" * 50 + "\n"
        report += f"{'总计':<8} {t['new_powder']:<6} {t['today_reply']:<6} " \
                 f"{t['today_register']:<6} {t['today_completed_training']:<6} " \
                 f"{t['today_withdraw']:<6} {t['today_new_order']:<6}\n"
        report += "```\n"

        report += "\n**📊 Section B: 累计总数 / Cumulative Totals**\n"
        report += "```\n"
        report += f"{'前台':<8} {'总粉':<6} {'总回复':<6} {'总注册':<6} {'总培训':<6} {'总提款':<6} {'总新单':<6}\n"
        report += "-" * 52 + "\n"

        for frontdesk, stats in sections['cumulative_totals'].items():
            report += f"{frontdesk:<8} {stats['total_powder']:<6} {stats['total_reply']:<6} " \
                     f"{stats['total_register']:<6} {stats['total_completed_training']:<6} " \
                     f"{stats['total_withdraw']:<6} {stats['total_new_order']:<6}\n"

        # Add totals row
        t = totals['cumulative_totals']
        report += "-" * 52 + "\n"
        report += f"{'总计':<8} {t['total_powder']:<6} {t['total_reply']:<6} " \
                 f"{t['total_register']:<6} {t['total_completed_training']:<6} " \
                 f"{t['total_withdraw']:<6} {t['total_new_order']:<6}\n"
        report += "```"

        return report

    async def generate_weekly_assessment_report(self, template: ReportTemplate) -> Dict[str, Any]:
        """Generate Type 5: Team Weekly Assessment Report."""
        team_name = template.team_name or template.parameters.get('team_name', '默认团队')

        # Calculate 5-day period
        end_date = template.parameters.get('end_date', date.today())
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        start_date = end_date - timedelta(days=4)

        date_range = f"{start_date.strftime('%-d/%-m/%Y')} - {end_date.strftime('%-d/%-m/%Y')}"

        # Get team members (this could be configured)
        team_members = template.parameters.get('members', ['阿YIM', '阿俊'])  # Default members

        assessment_data = {
            'team_name': team_name,
            'date_range': date_range,
            'start_date': start_date,
            'end_date': end_date,
            'members': {},
            'team_totals': {'daily_activity': {}, 'training_conversion': {}}
        }

        # Generate data for each team member
        for member in team_members:
            member_data = await self._generate_member_weekly_data(member, start_date, end_date)
            assessment_data['members'][member] = member_data

        # Calculate team totals
        assessment_data['team_totals'] = self._calculate_team_totals(assessment_data['members'])

        return {
            'report_type': 'weekly_assessment',
            'team_name': team_name,
            'date_range': date_range,
            'assessment_data': assessment_data,
            'formatted_report': self._format_weekly_assessment_report(assessment_data)
        }

    async def _generate_member_weekly_data(self, member: str, start_date: date, end_date: date) -> Dict[str, Any]:
        """Generate weekly data for a team member."""
        records = await database.get_client_records_by_frontdesk(member)

        daily_activity = []
        training_conversion = []

        for day_offset in range(5):
            current_date = start_date + timedelta(days=day_offset)
            date_str = current_date.strftime("%m月%d日")

            day_records = [r for r in records if r.date == date_str]

            # Daily Activity section
            activity = {
                'day': day_offset + 1,
                'date': current_date,
                'new_powder': len(day_records),
                'today_reply': len([r for r in day_records if r.first_day != '待定']),
                'today_register': len([r for r in day_records if r.first_day == '注册']),
                'today_completed_training': len([r for r in day_records if r.second_day == '注册']),
                'today_withdraw': 0,  # From financial records
                'today_new_order': 0  # From financial records
            }

            # Training Conversion section
            training = {
                'day': day_offset + 1,
                'date': current_date,
                'today_training': len([r for r in day_records if r.second_day == '注册']),
                'today_withdraw': 0,
                'today_not_withdraw': len([r for r in day_records if r.second_day == '注册']),
                'today_training_and_withdraw': 0,
                'today_new_order': 0
            }

            daily_activity.append(activity)
            training_conversion.append(training)

        # Calculate 5-day totals
        daily_totals = {}
        training_totals = {}

        for key in daily_activity[0].keys():
            if key not in ['day', 'date']:
                daily_totals[key] = sum(day[key] for day in daily_activity)

        for key in training_conversion[0].keys():
            if key not in ['day', 'date']:
                training_totals[key] = sum(day[key] for day in training_conversion)

        return {
            'daily_activity': daily_activity,
            'training_conversion': training_conversion,
            'daily_totals': daily_totals,
            'training_totals': training_totals
        }

    def _calculate_team_totals(self, members_data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
        """Calculate team totals from member data."""
        team_totals = {'daily_activity': {}, 'training_conversion': {}}

        if not members_data:
            return team_totals

        # Get keys from first member
        first_member = list(members_data.values())[0]
        daily_keys = first_member['daily_totals'].keys()
        training_keys = first_member['training_totals'].keys()

        # Calculate totals
        for key in daily_keys:
            team_totals['daily_activity'][key] = sum(
                member_data['daily_totals'].get(key, 0)
                for member_data in members_data.values()
            )

        for key in training_keys:
            team_totals['training_conversion'][key] = sum(
                member_data['training_totals'].get(key, 0)
                for member_data in members_data.values()
            )

        return team_totals

    def _format_weekly_assessment_report(self, assessment_data: Dict[str, Any]) -> str:
        """Format weekly assessment report."""
        report = f"""
👥 **团队5天考核 / 5-Day Team Assessment**

🏆 **团队 / Team:** {assessment_data['team_name']}
📅 **时间段 / Period:** {assessment_data['date_range']}

**📊 日常活动汇总 / Daily Activity Summary**
```
成员    新粉  回复  注册  培训  提款  新单
"""

        for member, data in assessment_data['members'].items():
            totals = data['daily_totals']
            report += f"{member:<6} {totals['new_powder']:<4} {totals['today_reply']:<4} " \
                     f"{totals['today_register']:<4} {totals['today_completed_training']:<4} " \
                     f"{totals['today_withdraw']:<4} {totals['today_new_order']:<4}\n"

        # Team totals
        team_daily = assessment_data['team_totals']['daily_activity']
        report += "-" * 35 + "\n"
        report += f"{'团队':<6} {team_daily.get('new_powder', 0):<4} {team_daily.get('today_reply', 0):<4} " \
                 f"{team_daily.get('today_register', 0):<4} {team_daily.get('today_completed_training', 0):<4} " \
                 f"{team_daily.get('today_withdraw', 0):<4} {team_daily.get('today_new_order', 0):<4}\n"

        report += "```\n\n**🎯 培训转换汇总 / Training Conversion Summary**\n```\n"
        report += "成员    培训  提款  未提  培训&提款 新单\n"

        for member, data in assessment_data['members'].items():
            totals = data['training_totals']
            report += f"{member:<6} {totals['today_training']:<4} {totals['today_withdraw']:<4} " \
                     f"{totals['today_not_withdraw']:<4} {totals['today_training_and_withdraw']:<8} " \
                     f"{totals['today_new_order']:<4}\n"

        # Team totals
        team_training = assessment_data['team_totals']['training_conversion']
        report += "-" * 35 + "\n"
        report += f"{'团队':<6} {team_training.get('today_training', 0):<4} {team_training.get('today_withdraw', 0):<4} " \
                 f"{team_training.get('today_not_withdraw', 0):<4} {team_training.get('today_training_and_withdraw', 0):<8} " \
                 f"{team_training.get('today_new_order', 0):<4}\n"

        report += "```"

        return report

    async def generate_performance_analysis_report(self, template: ReportTemplate) -> Dict[str, Any]:
        """Generate individual performance analysis report."""
        frontdesk_name = template.frontdesk or template.parameters.get('frontdesk')

        if not frontdesk_name:
            raise ValueError("Frontdesk name required for performance analysis")

        # Get performance data (reuse logic from handlers/performance.py)
        records = await database.get_client_records_by_frontdesk(frontdesk_name)

        if not records:
            return {
                'report_type': 'performance_analysis',
                'frontdesk': frontdesk_name,
                'error': 'No data found'
            }

        # Calculate metrics similar to performance handler
        today = date.today()
        today_str = today.strftime("%m月%d日")

        analysis = {
            'frontdesk': frontdesk_name,
            'total_clients': len(records),
            'today_clients': len([r for r in records if r.date == today_str]),
            'registration_rate': len([r for r in records if r.first_day == '注册']) / len(records) * 100 if records else 0,
            'response_rate': len([r for r in records if r.first_day != '待定']) / len(records) * 100 if records else 0
        }

        return {
            'report_type': 'performance_analysis',
            'frontdesk': frontdesk_name,
            'analysis': analysis,
            'formatted_report': self._format_performance_report(analysis)
        }

    def _format_performance_report(self, analysis: Dict[str, Any]) -> str:
        """Format performance analysis report."""
        return f"""
📈 **个人表现分析 / Performance Analysis**

👤 **前台 / Frontdesk:** {analysis['frontdesk']}

**📊 关键指标 / Key Metrics:**
• 总客户数 / Total Clients: {analysis['total_clients']}
• 今日新增 / Today New: {analysis['today_clients']}
• 注册率 / Registration Rate: {analysis['registration_rate']:.1f}%
• 响应率 / Response Rate: {analysis['response_rate']:.1f}%

**📈 表现评估 / Performance Assessment:**
{"📈 优秀" if analysis['registration_rate'] > 70 else "📊 良好" if analysis['registration_rate'] > 50 else "📉 需改进"}
        """

    async def generate_financial_overview_report(self, template: ReportTemplate) -> Dict[str, Any]:
        """Generate financial overview report."""
        target_date = template.parameters.get('date', date.today())
        if isinstance(target_date, str):
            target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

        date_str = target_date.strftime("%m月%d日")
        financial_records = await database.get_financial_records_by_date(date_str)

        # Calculate totals
        total_new_orders = sum(r.new_order_amount or 0 for r in financial_records)
        total_pressure = sum(r.pressure_amount or 0 for r in financial_records)
        total_income = sum(r.total_in or 0 for r in financial_records)

        return {
            'report_type': 'financial_overview',
            'date': target_date,
            'records_count': len(financial_records),
            'totals': {
                'new_orders': total_new_orders,
                'pressure': total_pressure,
                'income': total_income
            },
            'formatted_report': f"""
💰 **财务概览 / Financial Overview**
📅 **日期 / Date:** {target_date.strftime('%Y-%m-%d')}

• 记录数 / Records: {len(financial_records)}
• 新单总额 / New Orders: ${total_new_orders:.2f}
• 承压总额 / Pressure: ${total_pressure:.2f}
• 总收入 / Total Income: ${total_income:.2f}
            """
        }

    async def generate_client_status_report(self, template: ReportTemplate) -> Dict[str, Any]:
        """Generate client status report."""
        frontdesk = template.frontdesk or template.parameters.get('frontdesk')

        if frontdesk:
            records = await database.get_client_records_by_frontdesk(frontdesk)
        else:
            # All records with reasonable limit
            async with database.get_connection() as db:
                cursor = await db.execute("SELECT * FROM client_records ORDER BY created_at DESC LIMIT 5000")
                rows = await cursor.fetchall()
                records = [database._row_to_client_record(row) for row in rows if row]

        # Group by status
        status_counts = {
            'registered': len([r for r in records if r.first_day == '注册']),
            'not_registered': len([r for r in records if r.first_day == '不注册']),
            'pending_day1': len([r for r in records if r.first_day not in ['注册', '不注册']]),
            'pending_day2': len([r for r in records if r.second_day not in ['注册', '不注册']])
        }

        return {
            'report_type': 'client_status',
            'frontdesk': frontdesk,
            'total_clients': len(records),
            'status_breakdown': status_counts,
            'formatted_report': f"""
👥 **客户状态报告 / Client Status Report**
{"👤 前台: " + frontdesk if frontdesk else "📊 全体"}

• 总客户数 / Total: {len(records)}
• 已注册 / Registered: {status_counts['registered']}
• 未注册 / Not Registered: {status_counts['not_registered']}
• 待处理(第一天) / Pending Day 1: {status_counts['pending_day1']}
• 待处理(第二天) / Pending Day 2: {status_counts['pending_day2']}
            """
        }


# Global report engine instance
report_engine = ReportEngine()