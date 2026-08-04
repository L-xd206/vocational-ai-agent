/**
 * SidebarMenu Web Component
 * 若依框架侧边栏导航组件（支持分组 + 用户信息 + 退出登录）
 *
 * Usage:
 * <sidebar-menu
 *   title="导航菜单"
 *   default-open="系统管理"
 *   active="用户管理"
 *   user-name="管理员"
 *   user-role="超级管理员"
 *   logout-href="login.html">
 * </sidebar-menu>
 *
 * <script>
 * document.querySelector('sidebar-menu').setMenuData([
 *   {
 *     group: '主导航',
 *     items: [
 *       {
 *         label: '能力图谱',
 *         icon: 'network',
 *         children: [
 *           { label: '能力图谱库', href: '能力图谱库.html', active: true }
 *         ]
 *       }
 *     ]
 *   },
 *   {
 *     group: '系统管理',
 *     items: [
 *       {
 *         label: '系统管理',
 *         icon: 'cog',
 *         children: [
 *           { label: '用户管理', href: '#' }
 *         ]
 *       }
 *     ]
 *   }
 * ]);
 * </script>
 */

const ICONS = {
  cog: `<svg fill="none" viewBox="0 0 24 24" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"/></svg>`,
  home: `<svg fill="none" viewBox="0 0 24 24" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="m2.25 12 8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"/></svg>`,
  users: `<svg fill="none" viewBox="0 0 24 24" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z"/></svg>`,
  chart: `<svg fill="none" viewBox="0 0 24 24" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z"/></svg>`,
  doc: `<svg fill="none" viewBox="0 0 24 24" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z"/></svg>`,
  monitor: `<svg fill="none" viewBox="0 0 24 24" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M10.5 1.5H8.25A2.25 2.25 0 0 0 6 3.75v16.5a2.25 2.25 0 0 0 2.25 2.25h7.5A2.25 2.25 0 0 0 18 20.25V3.75a2.25 2.25 0 0 0-2.25-2.25H13.5m-3 0V3h3V1.5m-3 0h3m-3 18.75h3"/></svg>`,
  tool: `<svg fill="none" viewBox="0 0 24 24" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z"/></svg>`,
  network: `<svg fill="none" viewBox="0 0 24 24" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M7.5 14.25v2.25m3-4.5v4.5m3-6.75v6.75m3-9v9M6 20.25h12A2.25 2.25 0 0 0 20.25 18V6A2.25 2.25 0 0 0 18 3.75H6A2.25 2.25 0 0 0 3.75 6v12A2.25 2.25 0 0 0 6 20.25Z"/></svg>`,
  logout: `<svg fill="none" viewBox="0 0 24 24" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9"/></svg>`,
  user: `<svg fill="none" viewBox="0 0 24 24" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z"/></svg>`
};

const ARROW_ICON = `<svg class="arrow" fill="none" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5"/></svg>`;

class SidebarMenu extends HTMLElement {
  static get observedAttributes() {
    return ['title', 'active', 'default-open', 'user-name', 'user-role', 'logout-href'];
  }

  constructor() {
    super();
    this._menuData = [];
  }

  connectedCallback() {
    this.render();
    this.attachEvents();
  }

  attributeChangedCallback(name, oldVal, newVal) {
    if (oldVal !== newVal && this.isConnected) {
      this.render();
      this.attachEvents();
    }
  }

  /**
   * 设置菜单数据（支持分组格式）
   * @param {Array} data - 菜单配置数组
   *
   * 分组格式:
   * [
   *   {
   *     group: '主导航',
   *     items: [
   *       { label: '能力图谱', icon: 'network', children: [...] }
   *     ]
   *   },
   *   {
   *     group: '系统管理',
   *     items: [...]
   *   }
   * ]
   *
   * 兼容旧格式（无 group）:
   * [
   *   { label: '系统管理', icon: 'cog', children: [...] }
   * ]
   */
  setMenuData(data) {
    this._menuData = data;
    this.render();
    this.attachEvents();
  }

  getMenuData() {
    return this._menuData;
  }

  render() {
    const title = this.getAttribute('title') || '导航菜单';
    const activeLabel = this.getAttribute('active') || '';
    const defaultOpen = this.getAttribute('default-open') || '';
    const userName = this.getAttribute('user-name') || '管理员';
    const userRole = this.getAttribute('user-role') || '超级管理员';
    const logoutHref = this.getAttribute('logout-href') || 'login.html';

    const data = this._menuData.length > 0 ? this._menuData : this.parseFromSlots();

    // 判断是否为分组格式
    const isGrouped = data.length > 0 && data[0].group !== undefined;

    let menuHtml;
    if (isGrouped) {
      menuHtml = data.map((group, gIdx) => {
        const groupLabelHtml = group.group ? `<div class="menu-group-label">${escapeHtml(group.group)}</div>` : '';
        const itemsHtml = (group.items || []).map((item, idx) => this.renderMenuItem(item, gIdx + '-' + idx, activeLabel, defaultOpen)).join('');
        return groupLabelHtml + itemsHtml;
      }).join('');
    } else {
      menuHtml = `<div class="menu-group-label">${escapeHtml(title)}</div>` + data.map((item, idx) => this.renderMenuItem(item, idx, activeLabel, defaultOpen)).join('');
    }

    this.innerHTML = `
      <style>
        :host { display: block; }

        .sidebar {
          width: 220px;
          background: #FFFFFF;
          border-right: 1px solid #EDF2F7;
          position: fixed;
          top: 0;
          left: 0;
          bottom: 0;
          overflow-y: auto;
          z-index: 40;
          display: flex;
          flex-direction: column;
        }

        .sidebar::-webkit-scrollbar { width: 0; }

        /* 顶部系统标题 */
        .sidebar-header {
          background: linear-gradient(120deg, #DBEAFE 0%, #BFDBFE 30%, #93C5FD 60%, #A5B4FC 100%);
          padding: 20px;
          display: flex;
          align-items: center;
          gap: 12px;
          position: relative;
          overflow: hidden;
          flex-shrink: 0;
        }

        .sidebar-header::before {
          content: '';
          position: absolute;
          top: -40%;
          right: -30%;
          width: 120px;
          height: 120px;
          border-radius: 50%;
          background: rgba(255,255,255,0.25);
        }

        .header-icon {
          width: 36px;
          height: 36px;
          border: 1.5px solid rgba(30, 58, 95, 0.18);
          border-radius: 10px;
          display: flex;
          align-items: center;
          justify-content: center;
          position: relative;
          z-index: 1;
          background: rgba(255,255,255,0.35);
        }

        .header-icon svg {
          width: 20px;
          height: 20px;
          stroke: #3B82F6;
        }

        .header-text {
          position: relative;
          z-index: 1;
        }

        .header-title {
          font-size: 17px;
          font-weight: 700;
          color: #1E3A5F;
          letter-spacing: 2px;
          line-height: 1.2;
        }

        .header-subtitle {
          font-size: 10px;
          color: #1E3A5F;
          opacity: 0.55;
          letter-spacing: 0.5px;
          margin-top: 2px;
        }

        .menu-scroll {
          flex: 1;
          overflow-y: auto;
          padding: 8px 0;
        }

        .menu-scroll::-webkit-scrollbar { width: 0; }

        .menu-group-label {
          font-size: 11px;
          font-weight: 600;
          color: #A0AEC0;
          text-transform: uppercase;
          letter-spacing: 1px;
          padding: 12px 20px 6px;
        }

        .menu-group-label:first-child {
          padding-top: 0;
        }

        .menu-item { position: relative; }

        .menu-item-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 20px;
          cursor: pointer;
          transition: all 0.15s;
          user-select: none;
        }

        .menu-item-header:hover {
          background: #EFF6FF;
        }

        .menu-item-header svg {
          width: 18px;
          height: 18px;
          stroke: #4A5568;
          flex-shrink: 0;
          transition: stroke 0.15s;
        }

        .menu-item-header:hover svg {
          stroke: #3B82F6;
        }

        .menu-item-header span {
          flex: 1;
          font-size: 14px;
          color: #1A202C;
          font-weight: 400;
        }

        .menu-item-header .arrow {
          width: 16px;
          height: 16px;
          stroke: #CBD5E0;
          transition: transform 0.2s, stroke 0.15s;
        }

        .menu-item.open > .menu-item-header .arrow {
          transform: rotate(90deg);
          stroke: #3B82F6;
        }

        .menu-item.open > .menu-item-header svg {
          stroke: #3B82F6;
        }

        .sub-menu {
          max-height: 0;
          overflow: hidden;
          transition: max-height 0.25s ease;
        }

        .menu-item.open .sub-menu {
          max-height: 500px;
        }

        .sub-menu-item {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 9px 20px 9px 48px;
          font-size: 13px;
          color: #4A5568;
          cursor: pointer;
          transition: all 0.15s;
          text-decoration: none;
          position: relative;
          border: none;
          background: none;
          width: 100%;
          font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
          text-align: left;
        }

        .sub-menu-item::before {
          content: '';
          position: absolute;
          left: 28px;
          top: 50%;
          transform: translateY(-50%);
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #CBD5E0;
          transition: all 0.2s;
        }

        .sub-menu-item:hover {
          color: #3B82F6;
          background: #EFF6FF;
        }

        .sub-menu-item:hover::before {
          background: #3B82F6;
        }

        .sub-menu-item.active {
          color: #3B82F6;
          font-weight: 500;
          background: #EFF6FF;
        }

        .sub-menu-item.active::before {
          background: #3B82F6;
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
        }

        /* 底部用户信息 */
        .user-section {
          border-top: 1px solid #EDF2F7;
          padding: 12px 16px;
          flex-shrink: 0;
          position: relative;
        }

        .user-trigger {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 8px;
          border-radius: 10px;
          cursor: pointer;
          transition: background 0.15s;
          position: relative;
        }

        .user-trigger:hover {
          background: #F7FAFC;
        }

        .user-avatar {
          width: 36px;
          height: 36px;
          border-radius: 10px;
          background: linear-gradient(135deg, #93C5FD, #A5B4FC);
          display: flex;
          align-items: center;
          justify-content: center;
          color: #fff;
          font-size: 14px;
          font-weight: 700;
          flex-shrink: 0;
          letter-spacing: 1px;
        }

        .user-info {
          flex: 1;
          display: flex;
          flex-direction: column;
          min-width: 0;
        }

        .user-name {
          font-size: 13px;
          font-weight: 600;
          color: #1A202C;
          line-height: 1.2;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .user-role {
          font-size: 11px;
          color: #A0AEC0;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .user-trigger .arrow-down {
          width: 14px;
          height: 14px;
          stroke: #CBD5E0;
          transition: transform 0.2s;
          flex-shrink: 0;
        }

        .user-trigger.open .arrow-down {
          transform: rotate(180deg);
        }

        /* 用户下拉弹窗 */
        .user-dropdown {
          position: absolute;
          bottom: calc(100% + 8px);
          left: 12px;
          right: 12px;
          background: white;
          border-radius: 12px;
          box-shadow: 0 8px 24px rgba(0,0,0,0.1);
          border: 1px solid #EDF2F7;
          opacity: 0;
          visibility: hidden;
          transform: translateY(6px);
          transition: all 0.2s ease;
          overflow: hidden;
          z-index: 50;
        }

        .user-dropdown.show {
          opacity: 1;
          visibility: visible;
          transform: translateY(0);
        }

        .dropdown-item {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 11px 14px;
          font-size: 13px;
          color: #4A5568;
          cursor: pointer;
          transition: background 0.15s, color 0.15s;
          text-decoration: none;
          border: none;
          background: none;
          width: 100%;
          font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
          text-align: left;
        }

        .dropdown-item:hover {
          background: #EFF6FF;
          color: #3B82F6;
        }

        .dropdown-item svg {
          width: 16px;
          height: 16px;
          stroke: currentColor;
          flex-shrink: 0;
        }

        .dropdown-divider {
          height: 1px;
          background: #EDF2F7;
          margin: 3px 10px;
        }

        .dropdown-item.danger {
          color: #E53E3E;
        }

        .dropdown-item.danger:hover {
          background: #FFF5F5;
          color: #E53E3E;
        }
      </style>

      <nav class="sidebar">
        <div class="sidebar-header">
          <div class="header-icon">
            <svg fill="none" viewBox="0 0 24 24" stroke-width="1.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4.26 10.147a60.438 60.438 0 0 0-.491 6.347A48.62 48.62 0 0 1 12 20.904a48.62 48.62 0 0 1 8.232-4.41 60.46 60.46 0 0 0-.491-6.347m-15.482 0a50.636 50.636 0 0 0-2.658-.813A59.906 59.906 0 0 1 12 3.493a59.903 59.903 0 0 1 10.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0 1 12 13.489a50.702 50.702 0 0 1 7.74-3.342M6.75 15a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm0 0v-3.675A55.378 55.378 0 0 1 12 8.443m-7.007 11.55A5.981 5.981 0 0 0 6.75 15.75v-1.5"/>
            </svg>
          </div>
          <div class="header-text">
            <div class="header-title">教育实训</div>
            <div class="header-subtitle">Education & Training</div>
          </div>
        </div>

        <div class="menu-scroll">
          ${menuHtml}
        </div>

        <div class="user-section">
          <div class="user-trigger" id="userTrigger" onclick="this.closest('sidebar-menu').toggleUserDropdown()">
            <div class="user-avatar">${escapeHtml(userName.charAt(0))}</div>
            <div class="user-info">
              <span class="user-name">${escapeHtml(userName)}</span>
              <span class="user-role">${escapeHtml(userRole)}</span>
            </div>
            <svg class="arrow-down" fill="none" viewBox="0 0 24 24" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5"/>
            </svg>
          </div>
          <div class="user-dropdown" id="userDropdown">
            <button class="dropdown-item" onclick="this.closest('sidebar-menu').handleProfile()">
              ${ICONS.user}
              个人中心
            </button>
            <div class="dropdown-divider"></div>
            <button class="dropdown-item danger" onclick="this.closest('sidebar-menu').handleLogout()">
              ${ICONS.logout}
              退出登录
            </button>
          </div>
        </div>
      </nav>
    `;
  }

  renderMenuItem(item, index, activeLabel, defaultOpen) {
    const isOpen = item.label === defaultOpen || item.open ? 'open' : '';
    const iconSvg = ICONS[item.icon] || ICONS.cog;

    let childrenHtml = '';
    if (item.children && item.children.length > 0) {
      childrenHtml = `
        <div class="sub-menu">
          ${item.children.map(child => {
            const isActive = child.label === activeLabel || child.active ? 'active' : '';
            const href = child.href || 'javascript:void(0)';
            const clickHandler = child.onClick || '';
            return `<a class="sub-menu-item ${isActive}" href="${href}" data-label="${escapeHtml(child.label)}" ${clickHandler ? `onclick="${clickHandler}"` : ''}>${escapeHtml(child.label)}</a>`;
          }).join('')}
        </div>
      `;
    }

    return `
      <div class="menu-item ${isOpen}" data-index="${index}">
        <div class="menu-item-header" onclick="this.closest('sidebar-menu').toggleMenu(this)">
          ${iconSvg}
          <span>${escapeHtml(item.label)}</span>
          ${ARROW_ICON}
        </div>
        ${childrenHtml}
      </div>
    `;
  }

  parseFromSlots() {
    return [
      {
        label: '系统管理',
        icon: 'cog',
        open: true,
        children: [
          { label: '用户管理', href: '用户管理.html', active: true },
          { label: '角色管理', href: '#' },
          { label: '菜单管理', href: '#' }
        ]
      }
    ];
  }

  toggleMenu(header) {
    const item = header.parentElement;
    item.classList.toggle('open');

    const label = header.querySelector('span')?.textContent || '';
    this.dispatchEvent(new CustomEvent('menu-toggle', {
      detail: { label, isOpen: item.classList.contains('open'), item },
      bubbles: true
    }));
  }

  toggleUserDropdown() {
    const trigger = this.querySelector('#userTrigger');
    const dropdown = this.querySelector('#userDropdown');
    if (!trigger || !dropdown) return;
    const isOpen = dropdown.classList.contains('show');
    dropdown.classList.toggle('show');
    trigger.classList.toggle('open', !isOpen);
  }

  handleProfile() {
    const trigger = this.querySelector('#userTrigger');
    const dropdown = this.querySelector('#userDropdown');
    if (dropdown) dropdown.classList.remove('show');
    if (trigger) trigger.classList.remove('open');
    this.dispatchEvent(new CustomEvent('profile', {
      detail: {},
      bubbles: true
    }));
  }

  handleLogout() {
    this.dispatchEvent(new CustomEvent('logout', {
      detail: {},
      bubbles: true
    }));
    const logoutHref = this.getAttribute('logout-href') || 'login.html';
    window.location.href = logoutHref;
  }

  attachEvents() {
    const sidebar = this.querySelector('.sidebar');
    if (!sidebar) return;

    sidebar.addEventListener('click', (e) => {
      const subItem = e.target.closest('.sub-menu-item');
      if (!subItem) return;
      e.preventDefault();

      sidebar.querySelectorAll('.sub-menu-item').forEach(el => el.classList.remove('active'));
      subItem.classList.add('active');

      const label = subItem.getAttribute('data-label');
      this.dispatchEvent(new CustomEvent('menu-select', {
        detail: { label, href: subItem.getAttribute('href'), element: subItem },
        bubbles: true
      }));
    });

    // 点击外部关闭用户下拉
    const dropdown = this.querySelector('#userDropdown');
    const trigger = this.querySelector('#userTrigger');
    if (dropdown && trigger) {
      const closeDropdown = (e) => {
        if (!e.target.closest('.user-section')) {
          dropdown.classList.remove('show');
          trigger.classList.remove('open');
        }
      };
      document.addEventListener('click', closeDropdown);
      // 保存引用以便清理
      this._closeDropdownHandler = closeDropdown;
    }
  }
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

customElements.define('sidebar-menu', SidebarMenu);
