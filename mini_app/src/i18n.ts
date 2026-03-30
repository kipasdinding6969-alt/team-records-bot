const zh: Record<string, string> = {
  // Nav tabs
  tab_kanban: '看板',
  tab_today: '今日',
  tab_leaderboard: '排行榜',

  // Status labels
  status_new: '新客户',
  status_contacted: '已联系',
  status_replied: '有回复',
  status_registered: '已注册',
  status_training: '培训中',
  status_withdrew: '已撤回',
  status_ordered: '已下单',
  status_ghosted: '失联',
  status_blocked: '已屏蔽',
  status_scammed: '被骗',
  status_scheduled: '已预约',
  status_dead: '无效',

  // Client card
  client_no_phone: '无电话',
  client_deposited: '已存款',
  client_source: '来源',
  client_frontdesk: '前台',
  client_followup: '跟进',
  client_overdue: '已逾期',

  // Client detail
  detail_title: '客户详情',
  detail_notes: '备注',
  detail_deposits: '存款记录',
  detail_no_notes: '暂无备注',
  detail_no_deposits: '暂无存款',
  detail_change_status: '更新状态',
  detail_add_note: '添加备注',
  detail_note_placeholder: '输入备注...',
  detail_submit: '提交',
  detail_cancel: '取消',

  // Dashboard
  today_title: '今日概览',
  today_new_leads: '新客户',
  today_contacts: '已联系',
  today_orders: '新订单',
  today_overdue: '待跟进',
  today_active: '活跃客户',
  today_total: '总客户',
  today_pipeline: '各阶段客户数',

  // Leaderboard
  lb_title: '排行榜',
  lb_rank: '排名',
  lb_name: '姓名',
  lb_xp: '经验值',
  lb_streak: '连续天数',
  lb_leads: '今日新增',
  lb_orders: '今日订单',
  lb_badges: '徽章',

  // Actions
  action_update_status: '更新状态',
  action_add_note: '添加备注',

  // Loading / errors
  loading: '加载中...',
  error_load: '加载失败，请重试',
  error_update: '更新失败',
  success_updated: '更新成功',
  retry: '重试',

  // Status update confirm
  confirm_status_change: '确认将状态更改为',
}

const en: Record<string, string> = {
  tab_kanban: 'Pipeline',
  tab_today: 'Today',
  tab_leaderboard: 'Leaderboard',

  status_new: 'New',
  status_contacted: 'Contacted',
  status_replied: 'Replied',
  status_registered: 'Registered',
  status_training: 'Training',
  status_withdrew: 'Withdrew',
  status_ordered: 'Ordered',
  status_ghosted: 'Ghosted',
  status_blocked: 'Blocked',
  status_scammed: 'Scammed',
  status_scheduled: 'Scheduled',
  status_dead: 'Dead',

  client_no_phone: 'No phone',
  client_deposited: 'Deposited',
  client_source: 'Source',
  client_frontdesk: 'Staff',
  client_followup: 'Follow-up',
  client_overdue: 'Overdue',

  detail_title: 'Client Detail',
  detail_notes: 'Notes',
  detail_deposits: 'Deposits',
  detail_no_notes: 'No notes',
  detail_no_deposits: 'No deposits',
  detail_change_status: 'Change Status',
  detail_add_note: 'Add Note',
  detail_note_placeholder: 'Enter note...',
  detail_submit: 'Submit',
  detail_cancel: 'Cancel',

  today_title: "Today's Overview",
  today_new_leads: 'New Leads',
  today_contacts: 'Contacted',
  today_orders: 'Orders',
  today_overdue: 'Follow-ups Due',
  today_active: 'Active Clients',
  today_total: 'Total Clients',
  today_pipeline: 'Pipeline Counts',

  lb_title: 'Leaderboard',
  lb_rank: 'Rank',
  lb_name: 'Name',
  lb_xp: 'XP',
  lb_streak: 'Streak',
  lb_leads: "Today's Leads",
  lb_orders: "Today's Orders",
  lb_badges: 'Badges',

  action_update_status: 'Update Status',
  action_add_note: 'Add Note',

  loading: 'Loading...',
  error_load: 'Failed to load. Tap to retry.',
  error_update: 'Update failed',
  success_updated: 'Updated!',
  retry: 'Retry',

  confirm_status_change: 'Confirm status change to',
}

export function t(key: string, lang: string = 'zh'): string {
  const dict = lang === 'zh' ? zh : en
  return dict[key] ?? en[key] ?? key
}

export function statusLabel(status: string, lang: string = 'zh'): string {
  return t(`status_${status}`, lang) ?? status
}
