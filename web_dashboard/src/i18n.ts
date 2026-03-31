type Lang = 'zh' | 'en'

const LANG_KEY = 'dashboard_lang'

export function getLang(): Lang {
  return (localStorage.getItem(LANG_KEY) as Lang) || 'zh'
}

export function setLang(lang: Lang) {
  localStorage.setItem(LANG_KEY, lang)
}

const translations: Record<string, Record<Lang, string>> = {
  // Nav
  'nav.dashboard': { zh: '仪表盘', en: 'Dashboard' },
  'nav.pipeline': { zh: '漏斗管道', en: 'Pipeline' },
  'nav.team': { zh: '团队绩效', en: 'Team' },
  'nav.clients': { zh: '客户列表', en: 'Clients' },
  'nav.reports': { zh: '报告分析', en: 'Reports' },
  'nav.users': { zh: '用户管理', en: 'Users' },
  'nav.phone_lookup': { zh: '号码查询', en: 'Number Lookup' },
  'nav.permissions': { zh: '权限管理', en: 'Permissions' },
  'nav.brand': { zh: '团队记录', en: 'Team Records' },
  'nav.brand_sub': { zh: '管理看板', en: 'Manager Dashboard' },
  'nav.logout': { zh: '退出登录', en: 'Logout' },

  // Dashboard
  'dash.total_clients': { zh: '总客户', en: 'Total Clients' },
  'dash.active_clients': { zh: '活跃客户', en: 'Active Clients' },
  'dash.total_staff': { zh: '总员工', en: 'Total Staff' },
  'dash.total_deposits': { zh: '总充值', en: 'Total Deposits' },
  'dash.today_new': { zh: '今日新增', en: 'Today New' },
  'dash.today_contacts': { zh: '今日联系', en: 'Today Contacts' },
  'dash.today_orders': { zh: '今日下单', en: 'Today Orders' },
  'dash.today_deposits': { zh: '今日充值', en: 'Today Deposits' },
  'dash.overdue': { zh: '逾期跟进', en: 'Overdue Followups' },
  'dash.conversion': { zh: '转化率', en: 'Conversion Rate' },
  'dash.funnel': { zh: '转化漏斗', en: 'Conversion Funnel' },
  'dash.trends': { zh: '趋势', en: 'Trends' },
  'dash.new_clients_trend': { zh: '新客户趋势', en: 'New Clients Trend' },
  'dash.deposit_trend': { zh: '充值趋势', en: 'Deposit Trend' },
  'dash.recent_activity': { zh: '最近动态', en: 'Recent Activity' },
  'dash.loading': { zh: '加载中...', en: 'Loading...' },

  // Pipeline
  'pipeline.title': { zh: '漏斗管道', en: 'Pipeline' },
  'pipeline.loading': { zh: '加载管道数据...', en: 'Loading pipeline...' },

  // Team
  'team.title': { zh: '团队绩效', en: 'Team Performance' },
  'team.name': { zh: '姓名', en: 'Name' },
  'team.role': { zh: '角色', en: 'Role' },
  'team.team': { zh: '团队', en: 'Team' },
  'team.clients': { zh: '客户数', en: 'Clients' },
  'team.orders': { zh: '订单数', en: 'Orders' },
  'team.today_leads': { zh: '今日线索', en: 'Today Leads' },
  'team.today_orders': { zh: '今日订单', en: 'Today Orders' },
  'team.today_deposit': { zh: '今日充值', en: 'Today Deposit' },
  'team.xp': { zh: '经验值', en: 'XP' },
  'team.streak': { zh: '连续天数', en: 'Streak' },
  'team.loading': { zh: '加载中...', en: 'Loading...' },

  // Clients
  'clients.title': { zh: '客户列表', en: 'Client List' },
  'clients.search': { zh: '搜索电话/来源...', en: 'Search phone/source...' },
  'clients.all_status': { zh: '全部状态', en: 'All Status' },
  'clients.phone': { zh: '电话', en: 'Phone' },
  'clients.status': { zh: '状态', en: 'Status' },
  'clients.source': { zh: '来源', en: 'Source' },
  'clients.frontdesk': { zh: '前台', en: 'Frontdesk' },
  'clients.deposited': { zh: '已充值', en: 'Deposited' },
  'clients.created': { zh: '创建时间', en: 'Created' },
  'clients.no_results': { zh: '未找到客户', en: 'No clients found' },
  'clients.loading': { zh: '加载中...', en: 'Loading...' },
  'clients.prev': { zh: '上一页', en: 'Previous' },
  'clients.next': { zh: '下一页', en: 'Next' },

  // Client Detail
  'detail.info': { zh: '客户信息', en: 'Client Info' },
  'detail.phone': { zh: '电话', en: 'Phone' },
  'detail.source': { zh: '来源', en: 'Source' },
  'detail.frontdesk': { zh: '负责人', en: 'Frontdesk' },
  'detail.team': { zh: '团队', en: 'Team' },
  'detail.total_deposit': { zh: '总存款', en: 'Total Deposits' },
  'detail.created': { zh: '创建时间', en: 'Created' },
  'detail.milestones': { zh: '里程碑', en: 'Milestones' },
  'detail.contacted_at': { zh: '联系时间', en: 'Contacted' },
  'detail.replied_at': { zh: '回复时间', en: 'Replied' },
  'detail.registered_at': { zh: '注册时间', en: 'Registered' },
  'detail.training_at': { zh: '培训时间', en: 'Training' },
  'detail.first_order_at': { zh: '首次下单', en: 'First Order' },
  'detail.notes': { zh: '互动记录', en: 'Activity Log' },
  'detail.deposits': { zh: '充值记录', en: 'Deposits' },
  'detail.links': { zh: '关联客户', en: 'Linked Clients' },
  'detail.no_notes': { zh: '暂无备注', en: 'No notes' },
  'detail.no_deposits': { zh: '暂无充值', en: 'No deposits' },
  'detail.no_links': { zh: '暂无关联', en: 'No links' },
  'detail.add_link': { zh: '添加关联', en: 'Add Link' },
  'detail.back': { zh: '返回', en: 'Back' },
  'detail.link_type': { zh: '关联类型', en: 'Link Type' },
  'detail.link_note': { zh: '备注', en: 'Note' },
  'detail.target_client_id': { zh: '目标客户ID', en: 'Target Client ID' },
  'detail.remove_link': { zh: '移除', en: 'Remove' },
  'detail.system': { zh: '系统', en: 'System' },
  'detail.amount': { zh: '金额', en: 'Amount' },
  'detail.platform': { zh: '平台', en: 'Platform' },
  'detail.date': { zh: '日期', en: 'Date' },
  'link_type.related': { zh: '相关', en: 'Related' },
  'link_type.same_person': { zh: '同一人', en: 'Same Person' },
  'link_type.referral': { zh: '推荐', en: 'Referral' },
  'link_type.family': { zh: '家属', en: 'Family' },

  // Reports
  'reports.title': { zh: '报告分析', en: 'Reports' },
  'reports.export_clients': { zh: '导出客户', en: 'Export Clients' },
  'reports.export_report': { zh: '导出报告', en: 'Export Report' },
  'reports.daily': { zh: '每日', en: 'Daily' },
  'reports.weekly': { zh: '每周', en: 'Weekly' },
  'reports.monthly': { zh: '每月', en: 'Monthly' },

  // Users
  'users.title': { zh: '用户管理', en: 'User Management' },

  // Phone Lookup
  'phone.title': { zh: '号码查询', en: 'Number Lookup' },
  'phone.search_placeholder': { zh: '输入电话号码...', en: 'Enter phone number...' },
  'phone.search': { zh: '查询', en: 'Search' },
  'phone.owner': { zh: '所有者', en: 'Owner' },
  'phone.submitted_at': { zh: '提交时间', en: 'Submitted' },
  'phone.source': { zh: '来源', en: 'Source' },
  'phone.not_found': { zh: '号码未找到', en: 'Number not found' },
  'phone.history': { zh: '历史记录', en: 'History' },
  'phone.linked_clients': { zh: '关联客户', en: 'Linked Clients' },
  'phone.override': { zh: '覆盖所有权', en: 'Override Ownership' },
  'phone.stats': { zh: '统计', en: 'Statistics' },
  'phone.total_numbers': { zh: '总号码数', en: 'Total Numbers' },
  'phone.duplicates_blocked': { zh: '重复拦截', en: 'Duplicates Blocked' },

  // Permissions
  'perm.title': { zh: '权限管理', en: 'Permission Manager' },
  'perm.staff': { zh: '员工', en: 'Staff' },
  'perm.role': { zh: '角色', en: 'Role' },
  'perm.overrides': { zh: '覆盖权限', en: 'Overrides' },
  'perm.command': { zh: '命令', en: 'Command' },
  'perm.allowed': { zh: '允许', en: 'Allowed' },
  'perm.denied': { zh: '拒绝', en: 'Denied' },
  'perm.reason': { zh: '原因', en: 'Reason' },
  'perm.save': { zh: '保存', en: 'Save' },
  'perm.add_override': { zh: '添加覆盖', en: 'Add Override' },
  'perm.no_overrides': { zh: '无覆盖权限', en: 'No overrides' },
  'perm.loading': { zh: '加载中...', en: 'Loading...' },
  'perm.default_matrix': { zh: '默认权限矩阵', en: 'Default Permission Matrix' },
  'perm.all_commands': { zh: '所有命令', en: 'All Commands' },
  'perm.select_command': { zh: '选择命令...', en: 'Select command...' },
  'perm.frontdesk': { zh: '前台', en: 'Frontdesk' },
  'perm.leader': { zh: '组长', en: 'Leader' },
  'perm.admin': { zh: '管理员', en: 'Admin' },

  // Status labels
  'status.new': { zh: '新客户', en: 'New' },
  'status.contacted': { zh: '已联系', en: 'Contacted' },
  'status.replied': { zh: '已回复', en: 'Replied' },
  'status.registered': { zh: '已注册', en: 'Registered' },
  'status.training': { zh: '培训中', en: 'Training' },
  'status.withdrew': { zh: '已撤回', en: 'Withdrew' },
  'status.ordered': { zh: '已下单', en: 'Ordered' },
  'status.ghosted': { zh: '已消失', en: 'Ghosted' },
  'status.blocked': { zh: '已封锁', en: 'Blocked' },
  'status.scammed': { zh: '已诈骗', en: 'Scammed' },
  'status.scheduled': { zh: '已预约', en: 'Scheduled' },
  'status.dead': { zh: '已终止', en: 'Dead' },

  // Role labels
  'role.owner': { zh: '拥有者', en: 'Owner' },
  'role.admin': { zh: '管理员', en: 'Admin' },
  'role.member': { zh: '成员', en: 'Member' },

  // Theme
  'theme.dark': { zh: '暗色', en: 'Dark' },
  'theme.light': { zh: '亮色', en: 'Light' },

  // Common
  'common.loading': { zh: '加载中...', en: 'Loading...' },
  'common.error': { zh: '加载失败', en: 'Failed to load' },
  'common.save': { zh: '保存', en: 'Save' },
  'common.cancel': { zh: '取消', en: 'Cancel' },
  'common.delete': { zh: '删除', en: 'Delete' },
  'common.confirm': { zh: '确认', en: 'Confirm' },
  'common.search': { zh: '搜索', en: 'Search' },

  // Nav - Performance
  'nav.performance': { zh: '绩效看板', en: 'Performance' },

  // Performance Dashboard
  'perf.title': { zh: '绩效看板', en: 'Performance Dashboard' },
  'perf.no_data': { zh: '暂无数据', en: 'No data' },
  'perf.new_powder': { zh: '新粉丝', en: 'New Leads' },
  'perf.reply_rate': { zh: '回复率', en: 'Reply Rate' },
  'perf.register': { zh: '注册', en: 'Registered' },
  'perf.training': { zh: '培训', en: 'Training' },
  'perf.withdraw': { zh: '提款', en: 'Withdrew' },
  'perf.new_order': { zh: '新单', en: 'New Orders' },
  'perf.conversion': { zh: '转换率', en: 'Conversion' },
  'perf.deposit': { zh: '充值', en: 'Deposits' },
  'perf.dead': { zh: '死客', en: 'Dead' },
  'perf.team_total': { zh: '团队汇总', en: 'Team Totals' },

  // Client Detail enhancements
  'detail.add_note': { zh: '添加备注', en: 'Add Note' },
  'detail.note_placeholder': { zh: '写下备注内容...', en: 'Write a note...' },
  'detail.timeline': { zh: '时间线', en: 'Timeline' },
  'note_type.comment': { zh: '评论', en: 'Comment' },
  'note_type.flag': { zh: '标记', en: 'Flag' },
  'note_type.link_note': { zh: '关联备注', en: 'Link Note' },

  // Permission sections
  'perm.view_clients': { zh: '查看客户', en: 'View Clients' },
  'perm.edit_clients': { zh: '编辑客户', en: 'Edit Clients' },
  'perm.add_clients': { zh: '添加客户', en: 'Add Clients' },
  'perm.view_performance': { zh: '查看绩效', en: 'View Performance' },
  'perm.export_data': { zh: '导出数据', en: 'Export Data' },
  'perm.manage_team': { zh: '管理团队', en: 'Manage Team' },
  'perm.section_permissions': { zh: '功能权限', en: 'Section Permissions' },
}

export function t(key: string, lang?: Lang): string {
  const l = lang || getLang()
  const entry = translations[key]
  if (!entry) return key
  return entry[l] || entry['zh'] || key
}
