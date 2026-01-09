"""
比特浏览器窗口批量创建工具 - PyQt6 GUI版本
支持输入模板窗口ID，批量创建窗口，自动读取accounts.txt和proxies.txt
支持自定义平台URL和额外URL
支持列表显示现有窗口，并支持批量删除
UI布局调整：左侧操作区，右侧日志区
"""
import sys
import os
import threading
import pyotp
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QMessageBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QSplitter,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QIcon
from create_window import (
    read_accounts, read_proxies, get_browser_list, get_browser_info,
    delete_browsers_by_name, delete_browser_by_id, open_browser_by_id, create_browser_window, get_next_window_name
)
from run_playwright_google import process_browser

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)




DEFAULT_TEMPLATE_CONFIG = {
  "platform": "",
  "platformIcon": "",
  "url": "",
  "name": "默认模板",
  "userName": "",
  "password": "",
  "cookie": "",
  "otherCookie": "",
  "isGlobalProxyInfo": False,
  "isIpv6": False,
  "proxyMethod": 2,
  "proxyType": "noproxy",
  "ipCheckService": "ip2location",
  "host": "",
  "port": "",
  "proxyUserName": "",
  "proxyPassword": "",
  "enableSocks5Udp": False,
  "isIpNoChange": False,
  "isDynamicIpChangeIp": True,
  "status": 0,
  "isDelete": 0,
  "isMostCommon": 0,
  "isRemove": 0,
  "abortImage": False,
  "abortMedia": False,
  "stopWhileNetError": False,
  "stopWhileCountryChange": False,
  "syncTabs": False,
  "syncCookies": False,
  "syncIndexedDb": False,
  "syncBookmarks": False,
  "syncAuthorization": True,
  "syncHistory": False,
  "syncGoogleAccount": False,
  "allowedSignin": False,
  "syncSessions": False,
  "workbench": "localserver",
  "clearCacheFilesBeforeLaunch": True,
  "clearCookiesBeforeLaunch": False,
  "clearHistoriesBeforeLaunch": False,
  "randomFingerprint": True,
  "muteAudio": False,
  "disableGpu": False,
  "enableBackgroundMode": False,
  "syncExtensions": False,
  "syncUserExtensions": False,
  "syncLocalStorage": False,
  "credentialsEnableService": False,
  "disableTranslatePopup": False,
  "stopWhileIpChange": False,
  "disableClipboard": False,
  "disableNotifications": False,
  "memorySaver": False,
  "isRandomFinger": True,
  "isSynOpen": 1,
  "coreProduct": "chrome",
  "ostype": "PC",
  "os": "Win32",
  "coreVersion": "140"
}

class WorkerThread(QThread):
    """通用后台工作线程"""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)  # result data

    def __init__(self, task_type, **kwargs):
        super().__init__()
        self.task_type = task_type
        self.kwargs = kwargs
        self.is_running = True

    def stop(self):
        self.is_running = False

    def log(self, message):
        self.log_signal.emit(message)

    def msleep(self, ms):
        """可中断的sleep"""
        t = ms
        while t > 0 and self.is_running:
            time.sleep(0.1)
            t -= 100

    def run(self):
        if self.task_type == 'create':
            self.run_create()
        elif self.task_type == 'delete':
            self.run_delete()
        elif self.task_type == 'open':
            self.run_open()
        elif self.task_type == '2fa':
            self.run_2fa()
        elif self.task_type == 'sheerlink':
            self.run_sheerlink()

    def run_sheerlink(self):
        """执行SheerLink提取任务"""
        ids_to_process = self.kwargs.get('ids', [])
        if not ids_to_process:
             self.finished_signal.emit({'type': 'sheerlink', 'count': 0})
             return
        
        self.log(f"\n[开始] 提取 SheerID Link 任务，共 {len(ids_to_process)} 个窗口...")
        success_count = 0
        
        for i, browser_id in enumerate(ids_to_process, 1):
            if not self.is_running:
                self.log('[用户操作] 任务已停止')
                break
            
            self.log(f"正在处理 ({i}/{len(ids_to_process)}): {browser_id}")
            
            # Call the processing function (BLOCKING)
            success, msg = process_browser(browser_id)
            
            if success:
                self.log(f"[成功] {msg}")
                success_count += 1
            else:
                self.log(f"[失败] {msg}")
            
            # Delay between batches
            self.msleep(2000)
            
        self.log(f"[完成] 提取任务结束，成功 {success_count}/{len(ids_to_process)}")
        self.finished_signal.emit({'type': 'sheerlink', 'count': success_count})

    def run_open(self):
        """执行批量打开任务"""
        ids_to_open = self.kwargs.get('ids', [])
        if not ids_to_open:
            self.finished_signal.emit({'type': 'open', 'success_count': 0})
            return

        self.log(f"\n[开始] 准备打开 {len(ids_to_open)} 个窗口...")
        success_count = 0
        
        for i, browser_id in enumerate(ids_to_open, 1):
            if not self.is_running:
                self.log('[用户操作] 打开任务已停止')
                break
            
            self.log(f"正在打开 ({i}/{len(ids_to_open)}): {browser_id}")
            if open_browser_by_id(browser_id):
                self.log(f"[成功] 正在启动窗口 {browser_id}")
                success_count += 1
            else:
                self.log(f"[失败] 启动窗口 {browser_id} request失败")
            
            # 必需延迟防止API过载
            self.msleep(1000)
        
        self.log(f"[完成] 打开任务结束，成功请求 {success_count}/{len(ids_to_open)} 个")
        self.finished_signal.emit({'type': 'open', 'success_count': success_count})

    def run_2fa(self):
        """生成并保存2FA验证码"""
        try:
            self.log("正在通过API获取窗口列表和密钥...")
            
            # 1. 获取当前窗口列表 (尝试获取更多以涵盖所有)
            browsers = get_browser_list(page=0, pageSize=100)
            if not browsers:
                self.log("未获取到窗口列表")
                self.finished_signal.emit({'type': '2fa', 'codes': {}})
                return

            codes_map = {}
            file_lines = []
            
            count = 0
            for browser in browsers:
                if not self.is_running:
                    break
                
                # 优先从备注获取密钥 (第4段)
                secret = None
                remark = browser.get('remark', '')
                if remark:
                    parts = remark.split('----')
                    if len(parts) >= 4:
                        secret = parts[3].strip()
                
                # 如果备注没有，再尝试从字段获取
                if not secret:
                    secret = browser.get('faSecretKey')

                if secret and secret.strip():
                    try:
                        # 清理密钥
                        s = secret.strip().replace(" ", "")
                        totp = pyotp.TOTP(s)
                        code = totp.now()
                        
                        bid = browser.get('id')
                        codes_map[bid] = code
                        file_lines.append(f"{code}----{s}")
                        count += 1
                    except Exception as e:
                       # pass
                       pass
            
            # 保存到文件
            if file_lines:
                with open('2fa_codes.txt', 'w', encoding='utf-8') as f:
                    f.write('\n'.join(file_lines))
                self.log(f"已保存 {len(file_lines)} 个验证码到 2fa_codes.txt")
            
            self.log(f"2FA刷新完成，共生成 {count} 个")
            self.finished_signal.emit({'type': '2fa', 'codes': codes_map})
            
        except Exception as e:
            self.log(f"2FA处理异常: {e}")
            import traceback
            self.log(traceback.format_exc())
            self.finished_signal.emit({'type': '2fa', 'codes': {}})

    def run_delete(self):
        """执行批量删除任务"""
        ids_to_delete = self.kwargs.get('ids', [])
        if not ids_to_delete:
            self.finished_signal.emit({'success_count': 0, 'total': 0})
            return

        self.log(f"\n[开始] 准备删除 {len(ids_to_delete)} 个窗口...")
        success_count = 0
        
        for i, browser_id in enumerate(ids_to_delete, 1):
            if not self.is_running:
                self.log('[用户操作] 删除任务已停止')
                break
            
            self.log(f"正在删除 ({i}/{len(ids_to_delete)}): {browser_id}")
            if delete_browser_by_id(browser_id):
                self.log(f"[成功] 删除窗口 {browser_id}")
                success_count += 1
            else:
                self.log(f"[失败] 删除窗口 {browser_id} 失败")
        
        self.log(f"[完成] 删除任务结束，成功删除 {success_count}/{len(ids_to_delete)} 个")
        self.finished_signal.emit({'type': 'delete', 'success_count': success_count})

    def run_create(self):
        """执行创建任务"""
        template_id = self.kwargs.get('template_id')
        template_config = self.kwargs.get('template_config')
        
        platform_url = self.kwargs.get('platform_url')
        extra_url = self.kwargs.get('extra_url')
        name_prefix = self.kwargs.get('name_prefix')

        try:
            # 读取账户信息
            accounts_file = 'accounts.txt'
            accounts = read_accounts(accounts_file)
            
            if not accounts:
                self.log("[错误] 未找到有效的账户信息")
                self.log("请确保 accounts.txt 文件存在且格式正确")
                self.log("格式：邮箱----密码----辅助邮箱----2FA密钥")
                self.finished_signal.emit({'type': 'create', 'success_count': 0})
                return
            
            self.log(f"[信息] 找到 {len(accounts)} 个账户")
            
            # 读取代理信息
            proxies_file = 'proxies.txt'
            proxies = read_proxies(proxies_file)
            self.log(f"[信息] 找到 {len(proxies)} 个代理")
            
            # 获取参考窗口信息
            if template_config:
                reference_config = template_config
                ref_name = reference_config.get('name', '默认模板')
                self.log(f"[信息] 使用内置默认模板")
            else:
                reference_config = get_browser_info(template_id)
                if not reference_config:
                    self.log(f"[错误] 无法获取模板窗口配置")
                    self.finished_signal.emit({'type': 'create', 'success_count': 0})
                    return
                ref_name = reference_config.get('name', '未知')
                self.log(f"[信息] 使用模板窗口: {ref_name} (ID: {template_id})")
            
            # 显示平台和URL信息
            if platform_url:
                self.log(f"[信息] 平台URL: {platform_url}")
            if extra_url:
                self.log(f"[信息] 额外URL: {extra_url}")
            
            # 删除名称为"本地代理_2"的所有窗口（如果参考窗口是"本地代理_1"）
            if ref_name.startswith('本地代理_'):
                try:
                    next_name = get_next_window_name(ref_name)
                    # 如果下一个名称是"本地代理_2"，则尝试删除旧的"本地代理_2"
                    if next_name == "本地代理_2":
                        self.log(f"\n[步骤] 正在清理旧的'本地代理_2'窗口...")
                        deleted_count = delete_browsers_by_name("本地代理_2")
                        if deleted_count > 0:
                            self.log(f"[清理] 已删除 {deleted_count} 个旧窗口")
                except:
                    pass
            
            # 为每个账户创建窗口
            success_count = 0
            for i, account in enumerate(accounts, 1):
                if not self.is_running:
                    self.log("\n[用户操作] 创建任务已停止")
                    break
                
                self.log(f"\n{'='*40}")
                self.log(f"[进度] ({i}/{len(accounts)}) 创建: {account['email']}")
                
                # 获取对应的代理（如果有）
                proxy = proxies[i - 1] if i - 1 < len(proxies) else None
                
                browser_id, error_msg = create_browser_window(
                    account, 
                    template_id if not template_config else None,
                    proxy,
                    platform=platform_url if platform_url else None,
                    extra_url=extra_url if extra_url else None,
                    template_config=template_config,
                    name_prefix=name_prefix
                )
                
                if browser_id:
                    success_count += 1
                    self.log(f"[成功] 窗口创建成功！ID: {browser_id}")
                else:
                    self.log(f"[失败] 窗口创建失败: {error_msg}")
            
            self.log(f"\n{'='*40}")
            self.log(f"[完成] 总共创建 {success_count}/{len(accounts)} 个窗口")
            
            self.finished_signal.emit({'type': 'create', 'success_count': success_count})
            
        except Exception as e:
            self.log(f"[错误] 创建过程中发生异常: {e}")
            import traceback
            self.log(traceback.format_exc())
            self.finished_signal.emit({'type': 'create', 'success_count': 0})


class BrowserWindowCreatorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker_thread = None
        self.init_ui()
        
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("比特浏览器窗口管理工具")
        self.setWindowIcon(QIcon(resource_path("beta-1.svg")))
        self.resize(1200, 800)
        
        # 主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 主布局 - 水平
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)
        
        # ================== 左侧区域 (控制 + 列表) ==================
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_widget.setLayout(left_layout)
        
        # 1. 标题
        title_label = QLabel("控制面板")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        left_layout.addWidget(title_label)
        
        # 2. 配置区域
        config_group = QGroupBox("创建参数配置")
        config_layout = QVBoxLayout()
        
        # 模板ID
        input_layout1 = QHBoxLayout()
        input_layout1.addWidget(QLabel("模板窗口ID:"))
        self.template_id_input = QLineEdit()
        self.template_id_input.setPlaceholderText("请输入模板窗口ID")
        input_layout1.addWidget(self.template_id_input)
        config_layout.addLayout(input_layout1)

        # 窗口名前缀
        input_layout_prefix = QHBoxLayout()
        input_layout_prefix.addWidget(QLabel("窗口前缀:"))
        self.name_prefix_input = QLineEdit()
        self.name_prefix_input.setPlaceholderText("可选，默认按模板名或'默认模板'命名")
        input_layout_prefix.addWidget(self.name_prefix_input)
        config_layout.addLayout(input_layout_prefix)
        
        # URL配置
        input_layout2 = QHBoxLayout()
        input_layout2.addWidget(QLabel("平台URL:"))
        self.platform_url_input = QLineEdit()
        self.platform_url_input.setPlaceholderText("可选，平台URL")
        input_layout2.addWidget(self.platform_url_input)
        config_layout.addLayout(input_layout2)
        
        input_layout3 = QHBoxLayout()
        input_layout3.addWidget(QLabel("额外URL:"))
        self.extra_url_input = QLineEdit()
        self.extra_url_input.setPlaceholderText("可选，逗号分隔")
        input_layout3.addWidget(self.extra_url_input)
        config_layout.addLayout(input_layout3)
        
        # 文件路径提示
        file_info_layout = QHBoxLayout()
        self.accounts_label = QLabel("✅ accounts.txt")
        self.accounts_label.setStyleSheet("color: green;")
        self.proxies_label = QLabel("✅ proxies.txt")
        self.proxies_label.setStyleSheet("color: green;")
        file_info_layout.addWidget(self.accounts_label)
        file_info_layout.addWidget(self.proxies_label)
        file_info_layout.addStretch()
        config_layout.addLayout(file_info_layout)
        
        config_group.setLayout(config_layout)
        left_layout.addWidget(config_group)
        
        # 3. 创建控制按钮
        create_btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始根据模板创建窗口")
        self.start_btn.setFixedHeight(40)
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.start_btn.clicked.connect(self.start_creation)
        
        self.stop_btn = QPushButton("停止任务")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
        self.stop_btn.clicked.connect(self.stop_task)
        self.stop_btn.setEnabled(False)
        
        create_btn_layout.addWidget(self.start_btn)
        
        self.start_default_btn = QPushButton("使用默认模板创建")
        self.start_default_btn.setFixedHeight(40)
        self.start_default_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.start_default_btn.clicked.connect(self.start_creation_default)
        create_btn_layout.addWidget(self.start_default_btn)
        
        create_btn_layout.addWidget(self.stop_btn)
        left_layout.addLayout(create_btn_layout)
        
        # 4. 窗口列表部分
        list_group = QGroupBox("现存窗口列表")
        list_layout = QVBoxLayout()
        
        # 列表操作按钮
        list_action_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新列表")
        self.refresh_btn.clicked.connect(self.refresh_browser_list)
        
        self.btn_2fa = QPushButton("刷新并保存验证码")
        self.btn_2fa.setStyleSheet("color: purple; font-weight: bold;")
        self.btn_2fa.clicked.connect(self.action_refresh_2fa)

        self.btn_sheerlink = QPushButton("一键获取G-sheerlink")
        self.btn_sheerlink.setStyleSheet("color: green; font-weight: bold;")
        self.btn_sheerlink.clicked.connect(self.action_get_sheerlink)
        
        self.select_all_checkbox = QCheckBox("全选")
        self.select_all_checkbox.stateChanged.connect(self.toggle_select_all)
        
        self.open_btn = QPushButton("打开选中窗口")
        self.open_btn.setStyleSheet("color: blue; font-weight: bold;")
        self.open_btn.clicked.connect(self.open_selected_browsers)

        self.delete_btn = QPushButton("删除选中窗口")
        self.delete_btn.setStyleSheet("color: red;")
        self.delete_btn.clicked.connect(self.delete_selected_browsers)
        
        list_action_layout.addWidget(self.refresh_btn)
        list_action_layout.addWidget(self.btn_2fa)
        list_action_layout.addWidget(self.btn_sheerlink)
        list_action_layout.addWidget(self.select_all_checkbox)
        list_action_layout.addStretch()
        list_action_layout.addWidget(self.open_btn)
        list_action_layout.addWidget(self.delete_btn)
        list_layout.addLayout(list_action_layout)
        
        # 表格控件
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["选择", "名称", "窗口ID", "2FA验证码", "备注"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # Checkbox
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)      # Name
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)      # ID
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)      # 2FA
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)          # Remark
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        list_layout.addWidget(self.table)
        
        list_group.setLayout(list_layout)
        left_layout.addWidget(list_group)
        
        # 添加左侧到主布局
        main_layout.addWidget(left_widget, 3)
        
        # ================== 右侧区域 (日志) ==================
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_widget.setLayout(right_layout)
        
        log_label = QLabel("运行状态日志")
        log_label.setFont(title_font)
        right_layout.addWidget(log_label)
        
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setStyleSheet("background-color: #f5f5f5;")
        right_layout.addWidget(self.status_text)
        
        # 添加清除日志按钮
        clear_log_btn = QPushButton("清除日志")
        clear_log_btn.clicked.connect(self.status_text.clear)
        right_layout.addWidget(clear_log_btn)
        
        # 添加右侧到主布局
        main_layout.addWidget(right_widget, 2)
        
        # 初始加载
        QTimer.singleShot(100, self.refresh_browser_list)
        self.check_files()

    def check_files(self):
        """检查文件是否存在并更新UI"""
        accounts_exists = os.path.exists('accounts.txt')
        proxies_exists = os.path.exists('proxies.txt')
        
        if not accounts_exists:
            self.accounts_label.setText("❌ accounts.txt 缺失")
            self.accounts_label.setStyleSheet("color: red;")
        if not proxies_exists:
            self.proxies_label.setText("⚠️ proxies.txt 未找到")
            self.proxies_label.setStyleSheet("color: orange;")

    def log(self, message):
        """添加日志"""
        self.status_text.append(message)
        cursor = self.status_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.status_text.setTextCursor(cursor)

    def refresh_browser_list(self):
        """刷新窗口列表到表格"""
        self.table.setRowCount(0)
        self.select_all_checkbox.setChecked(False)
        self.log("正在刷新窗口列表...")
        QApplication.processEvents()
        
        try:
            browsers = get_browser_list()
            if not browsers:
                self.log("未获取到窗口列表")
                return
            
            self.table.setRowCount(len(browsers))
            for i, browser in enumerate(browsers):
                # Checkbox
                chk_item = QTableWidgetItem()
                chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                chk_item.setCheckState(Qt.CheckState.Unchecked)
                self.table.setItem(i, 0, chk_item)
                
                # Name
                name = str(browser.get('name', ''))
                self.table.setItem(i, 1, QTableWidgetItem(name))
                
                # ID
                bid = str(browser.get('id', ''))
                self.table.setItem(i, 2, QTableWidgetItem(bid))
                
                # 2FA (Initial empty)
                self.table.setItem(i, 3, QTableWidgetItem(""))
                
                # Remark
                remark = str(browser.get('remark', ''))
                self.table.setItem(i, 4, QTableWidgetItem(remark))
            
            self.log(f"列表刷新完成，共 {len(browsers)} 个窗口")
            
        except Exception as e:
            self.log(f"[错误] 刷新列表失败: {e}")

    def action_refresh_2fa(self):
        """刷新并保存2FA验证码"""
        self.log("正在获取所有窗口信息以生成验证码...")
        self.start_worker_thread('2fa')

    def action_get_sheerlink(self):
        """一键获取G-sheerlink"""
        ids = self.get_selected_browser_ids()
        if not ids:
            QMessageBox.warning(self, "提示", "请先在列表中勾选要处理的窗口")
            return
        
        reply = QMessageBox.question(self, '确认操作', 
                                    f"确定要对选中的 {len(ids)} 个窗口执行 SheerID 提取吗？\n该操作将逐个打开窗口、自动提取并关闭。",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.start_worker_thread('sheerlink', ids=ids)
        
    def open_selected_browsers(self):
        """打开选中的窗口"""
        ids = self.get_selected_browser_ids()
        if not ids:
            QMessageBox.warning(self, "提示", "请先勾选要打开的窗口")
            return
        
        self.start_worker_thread('open', ids=ids)

    def toggle_select_all(self, state):
        """全选/取消全选"""
        is_checked = (state == Qt.CheckState.Checked.value)  # value of Qt.CheckState.Checked is 2
        # 注意：Qt6中 state 是 int
        # 实际上 stateChanged 发出的是 int
        # Qt.CheckState.Checked.value 是 2
        
        row_count = self.table.rowCount()
        for i in range(row_count):
            item = self.table.item(i, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked if state == 2 else Qt.CheckState.Unchecked)

    def get_selected_browser_ids(self):
        """获取选中的窗口ID列表"""
        ids = []
        row_count = self.table.rowCount()
        for i in range(row_count):
            item = self.table.item(i, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                # ID is in column 2
                id_item = self.table.item(i, 2)
                if id_item:
                    ids.append(id_item.text())
        return ids

    def delete_selected_browsers(self):
        """删除选中的窗口"""
        ids = self.get_selected_browser_ids()
        if not ids:
            QMessageBox.warning(self, "提示", "请先勾选要删除的窗口")
            return
        
        reply = QMessageBox.question(
            self, 
            "确认删除", 
            f"确定要删除选中的 {len(ids)} 个窗口吗？\n此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.start_worker_thread('delete', ids=ids)

    def start_creation(self):
        """开始创建任务"""
        template_id = self.template_id_input.text().strip()
        if not template_id:
            QMessageBox.warning(self, "警告", "请输入模板窗口ID")
            return
            
        platform_url = self.platform_url_input.text().strip()
        extra_url = self.extra_url_input.text().strip()
        name_prefix = self.name_prefix_input.text().strip()
        
        self.update_ui_state(True)
        self.log(f"启动创建任务... 模板ID: {template_id}")
        
        self.worker_thread = WorkerThread(
            'create', 
            template_id=template_id,
            platform_url=platform_url, 
            extra_url=extra_url,
            name_prefix=name_prefix
        )
        self.worker_thread.log_signal.connect(self.log)
        self.worker_thread.finished_signal.connect(self.on_worker_finished)
        self.worker_thread.start()

    def start_worker_thread(self, task_type, **kwargs):
        """启动后台线程"""
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.warning(self, "提示", "当前有任务正在运行，请稍候...")
            return
            
        self.worker_thread = WorkerThread(task_type, **kwargs)
        self.worker_thread.log_signal.connect(self.log)
        self.worker_thread.finished_signal.connect(self.on_worker_finished)
        self.worker_thread.start()
        
        self.update_ui_state(running=True)

    def update_ui_state(self, running):
        """更新UI按钮状态"""
        self.start_btn.setEnabled(not running)
        self.start_default_btn.setEnabled(not running)
        self.delete_btn.setEnabled(not running)
        self.open_btn.setEnabled(not running)
        self.btn_2fa.setEnabled(not running)
        self.btn_sheerlink.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.refresh_btn.setEnabled(not running)
        self.template_id_input.setEnabled(not running)
        self.name_prefix_input.setEnabled(not running)

    def start_creation_default(self):
        """使用默认模板开始创建任务"""
        platform_url = self.platform_url_input.text().strip()
        extra_url = self.extra_url_input.text().strip()
        name_prefix = self.name_prefix_input.text().strip()
        
        self.update_ui_state(True)
        self.log(f"启动创建任务... 使用默认配置模板")
        
        self.start_worker_thread(
            'create', 
            template_config=DEFAULT_TEMPLATE_CONFIG,
            platform_url=platform_url, 
            extra_url=extra_url,
            name_prefix=name_prefix
        )

    def stop_task(self):
        """停止当前任务"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.stop()
            self.log("[用户操作] 正在停止任务...")
            self.stop_btn.setEnabled(False) #防止重复点击

    def on_worker_finished(self, result):
        """任务结束回调"""
        self.update_ui_state(running=False)
        self.log(f"任务已结束")
        
        # 如果是删除操作，完成后刷新列表
        if result.get('type') == 'delete':
            self.refresh_browser_list()
        # 如果是创建操作，也刷新列表可以看到新窗口
        elif result.get('type') == 'create':
            self.refresh_browser_list()
        # 2FA刷新结果
        elif result.get('type') == '2fa':
            codes = result.get('codes', {})
            row_count = self.table.rowCount()
            for i in range(row_count):
                id_item = self.table.item(i, 2) # ID Column
                if id_item:
                    bid = id_item.text()
                    if bid in codes:
                        self.table.setItem(i, 3, QTableWidgetItem(str(codes[bid])))
            QMessageBox.information(self, "完成", "2FA验证码已更新并保存")
        # 打开操作
        elif result.get('type') == 'open':
            pass
            
        elif result.get('type') == 'sheerlink':
            count = result.get('count', 0)
            QMessageBox.information(self, "完成", f"SheerLink 提取任务结束\n成功提取: {count} 个\n结果保存在 sheerIDlink.txt")

    def update_ui_state(self, running):
        """更新UI按钮状态"""
        self.start_btn.setEnabled(not running)
        self.delete_btn.setEnabled(not running)
        self.open_btn.setEnabled(not running)
        self.btn_2fa.setEnabled(not running)
        self.btn_sheerlink.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.refresh_btn.setEnabled(not running)


def main():
    app = QApplication(sys.argv)
    
    # 设置全局字体
    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)
    
    window = BrowserWindowCreatorGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
