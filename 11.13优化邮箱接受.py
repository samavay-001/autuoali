import asyncio
import random
import string
import logging
import requests
import contextvars
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tkinter import Tk, Label, Entry, Button, END, StringVar
from tkinter.scrolledtext import ScrolledText
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
from email import parser
from email.header import decode_header
from email.utils import parsedate_to_datetime
from faker import Faker
import chardet
import json
import imaplib
import email
import threading





# 创建一个带有重试机制的 requests.Session
def create_session_with_retry(retries=3, backoff_factor=0.3):
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

# 全局 session 对象，供所有请求使用
session = create_session_with_retry()

# 定义全局 contextvars 变量
container_name_var = contextvars.ContextVar('container_name', default='UnknownContainer')
container_code_var = contextvars.ContextVar('container_code', default='UnknownCode')

# 自定义日志过滤器，用于在日志记录中添加 containerName 和 containerCode
class ContainerFilter(logging.Filter):
    def filter(self, record):
        record.containerName = container_name_var.get()
        record.containerCode = container_code_var.get()
        return True

# 自定义日志格式化器，用于定义日志的输出格式
class CustomFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, 'containerName'):
            record.containerName = "UnknownContainer"
        if not hasattr(record, 'containerCode'):
            record.containerCode = "UnknownCode"
        return super().format(record)


# 配置日志记录
def configure_logging():
    formatter = CustomFormatter('%(asctime)s - %(containerName)s: %(containerCode)s - %(levelname)s - %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = []
    root_logger.addHandler(handler)

    # 添加过滤器
    root_logger.addFilter(ContainerFilter())



# 获取 containerName 和 containerCode
def get_container_info(container_code):
    env_list = get_environment_list(container_code)
    if env_list and env_list.get('code') == 0 and 'data' in env_list:
        env_info = env_list['data']['list'][0]
        container_name = env_info.get('containerName', 'UnknownContainer')
        return container_name, container_code
    return "UnknownContainer", container_code

# 获取环境列表
def get_environment_list(container_id):
    url = r'http://127.0.0.1:6873/api/v1/env/list'
    headers = {
        'Content-Type': 'application/json'
    }
    payload = {
        "containerCodes": [container_id],
        "current": 1,
        "size": 200
    }
    try:
        response = session.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as e:
            logging.error(f"JSON解析错误: {e}")
    except requests.exceptions.RequestException as e:
        logging.error(f"请求失败: {e}")

# 生成随机密码
def generate_password(min_length=8, max_length=10):
    if min_length > max_length:
        raise ValueError("min_length 必须小于或等于 max_length")

    length = random.randint(min_length, max_length)

    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits

    # 确保密码包含至少一个数字和一个字母
    password = [
        random.choice(lowercase + uppercase),  # 至少一个字母
        random.choice(digits)  # 至少一个数字
    ]

    all_characters = lowercase + uppercase + digits
    password += [random.choice(all_characters) for _ in range(length - 2)]

    random.shuffle(password)

    return ''.join(password)

# 生成随机用户名
def generate_username(min_length=5, max_length=8):
    length = random.randint(min_length, max_length)
    username = ''.join(random.choice(string.ascii_lowercase) for _ in range(length))
    return username

# 使用请求创建子邮箱
def create_sub_mail(token, group_pay_id, count):
    url = "http://121.199.27.26:5000/generate"  # 替换为实际服务器的IP地址或域名
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "token": token,
        "group_pay_id": group_pay_id,
        "count": count
    }

    try:
        response = session.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json().get('result')
    except requests.exceptions.RequestException as e:
        logging.error(f"请求创建子邮箱失败: {e}")
        return None

# 邮件客户端类，用于处理电子邮件的收发
class EmailClient:
    def __init__(self, email_address, password):
        self.email_address = email_address
        self.password = password
        self.imap_address = "domain-imap.cuiqiu.com"  # IMAP服务器地址
        self.port = 993  # SSL端口
        self.use_ssl = True  # 使用SSL加密连接
        self.emails = []

    # 获取电子邮件
    def fetch_emails(self):
        try:
            logging.info(f"连接到 {self.imap_address} 端口 {self.port}，使用SSL={self.use_ssl}")
            mail = imaplib.IMAP4_SSL(self.imap_address, self.port) if self.use_ssl else imaplib.IMAP4(self.imap_address,
                                                                                                      self.port)

            # 登录到邮件账户
            mail.login(self.email_address, self.password)
            logging.info("登录成功")

            # 选择邮件箱，"inbox" 是常见的邮箱文件夹
            mail.select("inbox")

            # 获取所有邮件ID
            result, data = mail.search(None, "ALL")  # 这里使用 ALL 你可以改成其他条件，例如 "UNSEEN"（未读邮件）

            if result != "OK":
                logging.error("获取邮件失败")
                return

            # 获取邮件ID列表
            email_ids = data[0].split()

            # 获取邮件的数量
            num_messages = len(email_ids)
            fetch_count = min(num_messages, 5)
            indices = list(range(num_messages, num_messages - fetch_count, -1))

            self.emails = []

            if fetch_count == 0:
                logging.info("没有新邮件")
                return

            logging.info(f"获取邮件... 总数 {num_messages}，获取最新的 {fetch_count} 封")

            for i, idx in enumerate(indices):
                # fetch() 获取邮件
                result, msg_data = mail.fetch(str(idx), "(RFC822)")

                if result != "OK":
                    logging.error(f"无法获取邮件 {i + 1}")
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        # 解码邮件主题
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding or "utf-8")
                        # 获取发件人
                        from_ = msg.get("From")
                        # 获取邮件日期
                        date_ = parsedate_to_datetime(msg.get("Date"))

                        self.emails.append(msg)
                        logging.info(f"邮件 {i + 1}: 来自: {from_}, 主题: {subject}, 日期: {date_}")

            mail.logout()  # 登出
            logging.info("邮件获取成功")
        except Exception as e:
            logging.error(f"获取邮件失败: {str(e)}")

    # 显示电子邮件的详细信息并提取验证码
    def show_email_details(self, index):
        if index >= len(self.emails):
            logging.error("无效的邮件索引")
            return None

        msg = self.emails[index]
        email_details = self.parse_email(msg)

        logging.info("邮件内容解析成功，可能包含敏感信息。")

        # 清理HTML内容，移除不需要的标签和样式
        email_details = re.sub(r'<img[^>]*>', '', email_details)
        email_details = re.sub(r'<style.*?>.*?</style>', '', email_details, flags=re.DOTALL)
        email_details = re.sub(r'transparent', '#FFFFFF', email_details)
        email_details = re.sub(r'rgb\([0-9,\s]+\)', '#000000', email_details)
        email_details = re.sub(r'\s+', ' ', email_details).strip()

        soup = BeautifulSoup(email_details, 'html.parser')
        verification_code = self.extract_verification_code(soup)
        if verification_code:
            logging.info(f"验证码: {verification_code}")
        else:
            logging.info("未找到验证码")
        return verification_code

    # 提取验证码
    def extract_verification_code(self, soup):
        code_span = soup.find('span', style=re.compile('color: #ff6600'))
        if code_span:
            return code_span.get_text()

        code_text = soup.find(text=re.compile(r'Verification Code: \d+'))
        if code_text:
            code = re.search(r'\d+', code_text)
            if code:
                return code.group()

        return None

    # 解析邮件内容
    def parse_email(self, msg):
        parts = []
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            if "attachment" in content_disposition:
                continue

            if content_type == "text/plain":
                text = part.get_payload(decode=True).decode('utf-8')
                text = text.replace('\n', '<br>')
                parts.append(f"<pre>{text}</pre>")
            elif content_type == "text/html":
                parts.append(part.get_payload(decode=True).decode("utf-8"))

        return "\n".join(parts)

# 模拟滑块验证的鼠标移动轨迹
async def move_mouse_randomly(page, start_x, start_y, end_x, end_y):
    steps = random.randint(50, 100)  # 增加随机步数
    distance_x = end_x - start_x
    distance_y = end_y - start_y
    for i in range(steps):
        x = start_x + (distance_x * i / steps) + random.uniform(-1, 1)  # 添加随机偏移
        y = start_y + (distance_y * i / steps) + random.uniform(-1, 1)
        await page.mouse.move(x, y, steps=random.randint(2, 6))
        await asyncio.sleep(random.uniform(0.01, 0.05))  # 随机等待
    await page.mouse.move(end_x, end_y)
    await page.mouse.up()
    await asyncio.sleep(random.uniform(0.5, 2))  # 滑动结束后再随机等待


# 执行滑块验证
async def perform_slider_verification(page):
    max_retries = 3
    retries = 0
    while retries < max_retries:
        try:
            # 确保页面滚动到顶部，避免页面不在最顶部导致无法找到元素
            await page.evaluate('window.scrollTo(0, 0)')
            await asyncio.sleep(1)  # 给滚动预留一些时间

            # 检查并刷新滑动验证
            refresh_button = await page.query_selector('a[href="javascript:noCaptcha.reset(2)"]')
            if refresh_button:
                logging.info("找到刷新链接，点击重试滑动验证")
                await move_and_click(page, refresh_button)
                await asyncio.sleep(random.uniform(2, 4))

            # 检查滑动验证是否已经通过
            if await page.query_selector('span.nc_iconfont.btn_ok'):
                logging.info("滑动验证已通过")
                return True  # 直接返回，避免重复检测

            # 滑块验证按钮
            slider_text = await page.wait_for_selector('span.nc-lang-cnt[data-nc-lang="_startTEXT"]', timeout=10000)
            slide_button = await page.wait_for_selector('span.nc_iconfont.btn_slide', timeout=10000)

            if slider_text and slide_button:
                # 确保滑动轨道存在
                slider_track = await page.query_selector('div#nc_2_n1z') or await page.query_selector('div#nc_2_n1t')
                if slider_track:
                    # 获取滑块和轨道的位置信息
                    slide_box = await slide_button.bounding_box()
                    track_box = await slider_track.bounding_box()

                    # 计算滑动距离
                    distance = track_box['width'] - slide_box['width']
                    start_x = slide_box['x'] + slide_box['width'] / 2
                    start_y = slide_box['y'] + slide_box['height'] / 2
                    end_x = start_x + distance
                    end_y = start_y

                    # 模拟滑动
                    await page.mouse.move(start_x, start_y)
                    await page.mouse.down()
                    await move_mouse_randomly(page, start_x, start_y, end_x, end_y)
                    await page.mouse.up()

                    # 检查是否成功通过验证
                    if await page.query_selector('span.nc_iconfont.btn_ok'):
                        logging.info("滑动验证通过")
                        return True  # 滑动成功后立即返回，避免进一步检测
                else:
                    logging.info("未找到滑轨")
                    retries += 1
                    if retries >= max_retries:
                        logging.info("多次未找到滑轨，刷新页面")
                        await page.reload()
                        await page.wait_for_load_state('domcontentloaded')
                        continue
            else:
                logging.info("未找到滑动验证元素")
                return False
        except Exception as e:
            logging.error(f"滑动验证执行出错: {e}")
            return False
    return False


# 获取浏览器上下文
async def get_browser_context(playwright, port):
    browser = await playwright.chromium.connect_over_cdp("http://127.0.0.1:" + str(port))
    context = browser.contexts[0]
    page = context.pages[0]
    await page.goto("about:blank")
    return context

# 接受Cookie弹窗
async def accept_cookies(page):
    try:
        gdpr_notice = await page.query_selector('div.GDPR-cookies-notice')
        if gdpr_notice:
            logging.info("发现GDPR通知，点击同意按钮")
            agree_button = await page.query_selector('div.gdpr-btn.gdpr-agree-btn')
            if agree_button:
                await agree_button.hover()
                await asyncio.sleep(random.uniform(0.5, 2))
                await agree_button.click()
                await asyncio.sleep(2)
            else:
                logging.info("GDPR同意按钮未找到")
        else:
            logging.info("GDPR通知未显示")
    except Exception as e:
        logging.error(f"接受GDPR cookies通知时出错: {e}")


# 修改后的 close_new_popup 函数，接受锁作为参数
async def close_new_popup(page, lock, max_retries=2, retry_delay=4):
    retries = 0
    popup_closed = False  # 标记是否关闭成功

    # 使用传入的锁对象
    async with lock:
        while retries < max_retries:
            if popup_closed:
                break

            try:
                # 查找新弹窗元素
                popup_element = await page.query_selector('div.mcfopu-rounded-6')
                if popup_element:
                    logging.info("发现新弹窗，准备关闭")
                    close_button = await page.query_selector('svg[width="40"][height="40"]')
                    if close_button:
                        await move_and_click(page, close_button)
                        logging.info("新弹窗已关闭")
                        popup_closed = True  # 标记为关闭成功
                        return True
                    else:
                        logging.info("未找到新弹窗的关闭按钮")
                        retries += 1
                else:
                    logging.info("未找到新弹窗，继续重试")
                    retries += 1

            except Exception as e:
                logging.error(f"关闭新弹窗时发生错误: {e}")

            if retries < max_retries and not popup_closed:
                logging.info(f"重试关闭弹窗，第 {retries} 次，等待 {retry_delay} 秒...")
                await asyncio.sleep(retry_delay)

        if not popup_closed:
            logging.error(f"在 {max_retries} 次尝试后，仍未成功关闭新弹窗")

    return popup_closed


# 滚动到底部
async def scroll_to_bottom(page, check_gdpr_popup_task, lock):
    previous_height = None
    max_attempts = 10  # 尝试次数上限
    attempts = 0

    while attempts < max_attempts:
        current_height = await page.evaluate("document.body.scrollHeight")

        await page.mouse.wheel(0, current_height)
        await asyncio.sleep(random.uniform(0.5, 1))

        # 在下滑过程中检测新弹窗，增加重试
        await close_new_popup(page, lock, max_retries=3, retry_delay=2)  # 在滚动过程中指定重试次数和间隔

        if check_gdpr_popup_task.done():
            logging.info("GDPR弹窗已经处理完毕")
            break

        if previous_height is not None and previous_height == current_height:
            logging.info("页面高度稳定，停止滚动")
            break
        else:
            previous_height = current_height

        await asyncio.sleep(5)
        attempts += 1

    if attempts >= max_attempts:
        logging.warning("页面未能稳定在最底部，尝试次数达到上限")

    logging.info("页面已滚动到底部并稳定。")

    # 到达页面底部后再检测一次新弹窗
    await close_new_popup(page, lock, max_retries=3, retry_delay=2)  # 最后再检测一次新弹窗



# 新增检测并处理 a[href="//www.alibaba.com?tracelog=ma_oversea_top_alibaba"] 逻辑
# 修改后的检测和处理 Alibaba 链接逻辑
async def detect_and_handle_alibaba_link(page, registration_info, retries=3):
    for attempt in range(retries):
        try:
            alibaba_link = await page.wait_for_selector('a[href="//www.alibaba.com?tracelog=ma_oversea_top_alibaba"]', timeout=10000)
            if alibaba_link:
                logging.info("检测到 Alibaba 链接，准备执行后续操作")
                await alibaba_link.click()
                await page.wait_for_load_state('domcontentloaded', timeout=60000)
                return True  # 链接已成功点击，后续逻辑可继续
            else:
                logging.info(f"未检测到 Alibaba 链接，重试第 {attempt + 1}/{retries}")
        except PlaywrightTimeoutError:
            logging.error(f"检测或点击 Alibaba 链接时发生超时错误，重试第 {attempt + 1}/{retries}")
        except Exception as e:
            logging.error(f"检测 Alibaba 链接时发生错误: {e}")

        # 刷新页面并继续检测
        try:
            logging.info("未检测到 Alibaba 链接，刷新页面并继续重试")
            await page.reload()  # 刷新页面
            await page.wait_for_load_state('domcontentloaded', timeout=60000)

            # 检查是否跳转到登录页面
            if "login.alibaba.com" in page.url:
                logging.info("页面跳转到登录页面，准备重新登录")
                await handle_login(page, registration_info)  # 执行登录逻辑
                await page.wait_for_load_state('domcontentloaded', timeout=60000)  # 等待登录后的页面加载
                continue  # 登录成功后继续检测 Alibaba 链接
        except PlaywrightTimeoutError:
            logging.error(f"刷新页面时发生超时错误，重试第 {attempt + 1}/{retries}")
        except Exception as e:
            logging.error(f"刷新页面时发生错误: {e}")

        # 重试等待时间
        await asyncio.sleep(5)

    logging.error("多次尝试后仍未成功检测到 Alibaba 链接，流程停止")
    return False  # 无法找到链接则返回 False



# 检查并刷新滑动验证页面
async def check_and_refresh(page, selector, retries=3):
    for attempt in range(retries):
        try:
            element = await page.wait_for_selector(selector, timeout=20000)
            if element:
                logging.info(f"找到了目标元素: {selector}")
                return element
        except PlaywrightTimeoutError:
            logging.warning(f"未找到目标元素: {selector}，重试第 {attempt + 1}/{retries} 次")
            await asyncio.sleep(10)  # 在每次重试之间增加一点等待时间

    logging.error(f"多次尝试后仍未找到目标元素: {selector}")
    # 不再刷新页面
    return None

# 新增处理登录逻辑
async def handle_login(page, registration_info):
    try:
        # 等待账号输入框并填写账号
        email_input = await page.wait_for_selector('input[name="account"]', timeout=10000)
        await email_input.fill(registration_info['email'])
        logging.info(f"填写账号: {registration_info['email']}")

        # 等待密码输入框并填写密码
        password_input = await page.wait_for_selector('input[name="password"]', timeout=10000)
        await password_input.fill(registration_info['password'])
        logging.info(f"填写密码")

        # 点击登录按钮
        sign_in_button = await page.wait_for_selector('button.sif_form-submit', timeout=10000)
        await sign_in_button.click()
        logging.info("点击登录按钮")

        # 等待页面跳转完成
        await page.wait_for_load_state('domcontentloaded', timeout=60000)
        logging.info("登录成功，页面已加载")

    except PlaywrightTimeoutError:
        logging.error("登录页面元素超时未检测到")
    except Exception as e:
        logging.error(f"处理登录时发生错误: {e}")

# 模拟鼠标移动轨迹并点击目标元素
async def move_and_click(page_or_frame, element):
    try:
        # 如果element是在iframe内，page_or_frame会是iframe的对象。通过page_or_frame.page获取顶级page对象。
        page = page_or_frame.page if hasattr(page_or_frame, 'page') else page_or_frame

        # 确保元素滚动到可见区域
        await element.scroll_into_view_if_needed()

        # 尝试执行 hover 操作
        try:
            await element.hover(timeout=30000)
        except PlaywrightTimeoutError as e:
            logging.warning(f"Hover 操作超时，尝试使用 force=True 进行操作: {e}")
            await element.hover(force=True)

        # 获取元素的边界框
        box = await element.bounding_box()

        if box is None:
            logging.error("无法获取元素的边界框，元素可能不可见或不存在")
            return

        # 计算点击位置为元素的中心点
        x = box['x'] + box['width'] / 2
        y = box['y'] + box['height'] / 2

        # 随机移动到元素位置，然后点击
        await page.mouse.move(x, y, steps=random.randint(10, 25))
        await asyncio.sleep(random.uniform(0.2, 0.5))  # 添加随机延迟
        await page.mouse.click(x, y)
        logging.info("移动并点击了目标元素")
    except Exception as e:
        logging.error(f"在移动和点击操作中发生错误: {e}")

# 处理 'Next' 按钮的点击并等待页面加载
async def handle_next_button_and_wait_for_element(iframe_content, next_button_selector, target_element_selector):
    try:
        next_button = await iframe_content.wait_for_selector(next_button_selector, timeout=20000)
        if next_button:
            await move_and_click(iframe_content, next_button)
            logging.info("点击了'Next'按钮")

            await asyncio.sleep(5)  # 额外的延时等待

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await iframe_content.wait_for_load_state('networkidle')
                    logging.info("新页面加载完成")

                    target_element = await iframe_content.wait_for_selector(target_element_selector, timeout=15000)
                    if target_element:
                        logging.info("成功找到目标元素")
                        return target_element
                    else:
                        logging.warning(f"未找到目标元素，尝试第 {attempt + 1} 次")
                        await asyncio.sleep(5)
                except PlaywrightTimeoutError:
                    logging.warning(f"页面加载超时，第 {attempt + 1} 次重试...")
                    if attempt == max_retries - 1:
                        logging.error("页面加载失败，停止重试")
                        return None

        logging.error("未找到 'Next' 按钮")
        return None
    except Exception as e:
        logging.error(f"处理 'Next' 按钮后的页面加载时出错: {e}")

# 查找 'Membership program' 链接并点击
async def find_and_click_membership_program(page):
    max_attempts = 5  # 尝试次数上限
    for attempt in range(max_attempts):
        try:
            membership_program_link = await page.wait_for_selector('text=Membership program', timeout=15000)
            if membership_program_link:
                await move_and_click(page, membership_program_link)
                logging.info("Clicked 'Membership program'")
                return True
            else:
                logging.warning(f"未找到 'Membership program' 链接，尝试第 {attempt + 1}/{max_attempts} 次")
        except PlaywrightTimeoutError:
            logging.warning(f"查找 'Membership program' 超时，第 {attempt + 1}/{max_attempts} 次尝试")

        await asyncio.sleep(2)
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight);')
        await asyncio.sleep(random.uniform(1, 3))  # 增加等待时间，确保页面加载完成

    logging.error("多次尝试后仍未找到 'Membership program' 链接")
    return False


# 尝试重新附加 iframe 的函数
async def reattach_frame(page):
    try:
        iframe = await page.wait_for_selector('iframe#bbp-iframe', timeout=20000)  # 根据实际的 iframe ID 进行选择器调整
        if iframe:
            logging.info("成功重新附加 iframe")
            return await iframe.content_frame()  # 返回 iframe 的内容框架
        else:
            logging.error("未能找到 iframe")
            return None
    except Exception as e:
        logging.error(f"重新附加 iframe 时出错: {e}")
        return None



# 新增的函数，检测并处理 'Online retailer' 元素
async def handle_online_retailer(iframe_content, new_page):
    max_retries = 3  # 设置最大重试次数
    for attempt in range(max_retries):
        try:
            online_retailer = await iframe_content.wait_for_selector('text=Online retailer', timeout=30000)
            if online_retailer:
                await move_and_click(iframe_content, online_retailer)
                logging.info("点击了 'Online retailer' 元素")
                return True  # 找到并点击后，立即返回成功
        except PlaywrightTimeoutError:
            logging.warning(f"未能找到 'Online retailer' 元素，第 {attempt + 1}/{max_retries} 次尝试")
            if attempt < max_retries - 1:
                logging.info("重新加载页面并重试")
                await new_page.reload()  # 刷新页面
                await new_page.wait_for_load_state("domcontentloaded", timeout=60000)

                # 刷新后，先点击 "Unlock your stage"
                unlock_button = await new_page.wait_for_selector('div.banner-button.banner-button-unlock',
                                                                 timeout=20000)
                if unlock_button:
                    await move_and_click(new_page, unlock_button)
                    logging.info("点击了 'Unlock your stage' 按钮")
                else:
                    logging.error("刷新后未能找到 'Unlock your stage' 按钮")
                    continue  # 如果找不到 "Unlock your stage" 按钮，直接跳过这次循环

                # 点击 "Unlock your stage" 后重新获取 iframe 内容
                iframe = await new_page.wait_for_selector('iframe#bbp-iframe', timeout=20000)
                iframe_content = await iframe.content_frame()

                await asyncio.sleep(random.uniform(3, 5))  # 添加随机延时，模拟真实操作
        except Exception as e:
            if "Frame was detached" in str(e):
                logging.error("Frame was detached, attempting to reattach...")
                iframe_content = await reattach_frame(new_page)  # 尝试重新附加 iframe
                if not iframe_content:
                    logging.error("Failed to reattach frame")
                    return False
            else:
                logging.error(f"处理 'Online retailer' 时出错: {e}")
                return False
    logging.error("多次尝试后仍未找到 'Online retailer' 元素")
    return False  # 如果多次尝试都失败，则返回 False


# 执行额外操作

# 在执行额外操作时创建新的锁对象并传递给函数
async def perform_additional_actions(page, registration_info):
    logging.info("开始执行额外操作...")

    lock = asyncio.Lock()  # 在当前任务中创建新的锁对象

    try:
        # 监控并处理 GDPR 弹窗
        async def monitor_gdpr_popup(page, lock, check_interval=1, max_duration=15):
            total_wait_time = 0
            while total_wait_time < max_duration:
                try:
                    gdpr_notice = await page.query_selector('div.GDPR-cookies-notice')
                    if gdpr_notice:
                        logging.info("发现GDPR通知，点击同意按钮")
                        agree_button = await page.query_selector('div.gdpr-btn.gdpr-agree-btn')
                        if agree_button:
                            await move_and_click(page, agree_button)
                            await asyncio.sleep(2)
                            logging.info("GDPR同意按钮已点击")
                        break
                except PlaywrightTimeoutError:
                    pass
                await asyncio.sleep(check_interval)
                total_wait_time += check_interval

            if total_wait_time >= max_duration:
                logging.info("达到最大等待时间，未检测到GDPR弹窗")

        # 监控 GDPR 弹窗
        gdpr_task = asyncio.create_task(monitor_gdpr_popup(page, lock))

        # 滚动页面到底部
        await scroll_to_bottom(page, gdpr_task, lock)
        await gdpr_task

        # 处理 'Membership program' 链接并点击
        async with page.expect_popup() as popup_info:
            if await find_and_click_membership_program(page):
                logging.info("Clicked 'Membership program' successfully.")
            else:
                logging.error("Failed to click 'Membership program' after multiple attempts.")
                return  # 如果失败，不需要继续

        new_page = await popup_info.value
        await new_page.bring_to_front()
        logging.info("新标签页已打开")
        await new_page.wait_for_load_state("domcontentloaded", timeout=60000)

        # 点击 'Unlock your stage' 按钮
        unlock_button = await new_page.wait_for_selector('div.banner-button.banner-button-unlock', timeout=20000)
        if unlock_button:
            await move_and_click(new_page, unlock_button)
            logging.info("点击了 'Unlock your stage' 按钮")

            iframe = await new_page.wait_for_selector('iframe#bbp-iframe', timeout=20000)
            iframe_content = await iframe.content_frame()

            # 调用 handle_online_retailer 函数，处理 iFrame 弹窗中的 'Online retailer' 元素
            if not await handle_online_retailer(iframe_content, new_page):
                logging.error("操作失败，未能找到 'Online retailer' 元素")
                return
        else:
            logging.error("未找到 'Unlock your stage' 按钮")
            return

        # 处理 'Next' 按钮后的操作
        await handle_next_button_and_wait_for_element(
            iframe_content,
            next_button_selector='div.footer-button.false',
            target_element_selector='#shopName'
        )

        # 填写随机生成的商店名称
        random_shop_name = generate_username(8, 10)
        shop_name_input = await iframe_content.wait_for_selector('#shopName', timeout=10000)
        await shop_name_input.fill(random_shop_name)
        logging.info(f"输入随机商店名称: {random_shop_name}")

        await asyncio.sleep(random.uniform(2, 5))

        # 填写商店链接
        shop_link_input = await iframe_content.wait_for_selector('#shopLink', timeout=10000)
        shop_link = f"www.{random_shop_name}.com"
        await shop_link_input.fill(shop_link)
        logging.info(f"输入商店链接: {shop_link}")

        # 点击确认按钮
        confirm_button = await iframe_content.wait_for_selector('svg.bbp-icon-font[width="18"]', timeout=10000)
        await move_and_click(iframe_content, confirm_button)
        logging.info("点击了确认按钮")

        # 点击 'Next' 按钮
        next_button_after_confirm = await iframe_content.wait_for_selector('div.footer-button.false', timeout=10000)
        await move_and_click(iframe_content, next_button_after_confirm)
        logging.info("点击了 'Next' 按钮")

        await new_page.wait_for_load_state("domcontentloaded")  # 使用 new_page 而不是 iframe_content
        logging.info("页面加载完成")

        # 检查是否存在关闭按钮并点击
        close_button = await iframe_content.wait_for_selector('svg.bbp-icon-font.header-close', timeout=10000)
        if close_button:
            await close_button.click()
            logging.info("点击了关闭按钮")

            # 更新环境备注信息
            update_env_remark(registration_info['containerCode'],
                              f"认证完成,注册完成, 账号: {registration_info['email']}, 密码: {registration_info['password']}")
            logging.info("环境备注信息已更新")

            # 跳转到 Alibaba 主页
            await page.goto("https://www.alibaba.com")
            logging.info("页面跳转至 https://www.alibaba.com")

            # 关闭所有非主页标签页
            pages = page.context.pages
            for p in pages:
                if p != page:
                    await p.close()
                    logging.info("关闭了其他标签页")
    except Exception as e:
        logging.error(f"执行额外操作时出错: {e}")


# 勾选用户协议
async def check_user_agreement(page):
    try:
        # 等待用户协议复选框加载
        await page.wait_for_selector('input[name="memberAgreement"]', timeout=10000)

        # 获取用户协议复选框元素
        agreement_checkbox = await page.query_selector('input[name="memberAgreement"]')

        if agreement_checkbox:
            # 设置重试次数
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # 尝试点击复选框
                    await move_and_click(page, agreement_checkbox)

                    # 检查是否勾选成功
                    is_checked = await page.evaluate(
                        '(element) => element.checked || element.value === "true"',
                        agreement_checkbox
                    )

                    if is_checked:
                        logging.info("Successfully checked the user agreement.")
                        return True
                    else:
                        logging.warning(
                            f"User agreement not checked. Retrying... Attempt {attempt + 1} of {max_attempts}")

                    # 随机延时，模拟人类行为
                    await asyncio.sleep(random.uniform(0.5, 2))
                except Exception as e:
                    logging.error(f"Attempt {attempt + 1} to check user agreement failed: {e}")

            logging.error("Failed to check user agreement after multiple attempts.")
            return False
        else:
            logging.error("User agreement checkbox not found.")
            return False
    except Exception as e:
        logging.error(f"Error while checking user agreement: {e}")
        return False

# 确认用户协议已勾选并点击注册按钮
async def confirm_and_click_register_button(registration_popup):
    try:
        # 检查用户协议复选框是否被勾选
        if not await check_user_agreement(registration_popup):
            logging.error("User agreement checkbox is not checked. Aborting registration.")
            return "User agreement checkbox is not checked"

        # 点击注册按钮
        register_button = await registration_popup.query_selector('button.RP-form-submit')
        if register_button:
            await move_and_click(registration_popup, register_button)
            logging.info("Clicked register button")

            # 随机延时，模拟人类操作
            await asyncio.sleep(random.uniform(5, 15))
            return "Proceeding with registration"
        else:
            logging.error("Register button not found")
            return "Register button not found"
    except Exception as e:
        logging.error(f"Error in confirm_and_click_register_button: {e}")
        return "Error during registration button click"

# 打开Alibaba页面并执行注册
async def open_alibaba(browser_context, registration_info, email_client):
    page = browser_context.pages[0]

    try:
        # 尝试访问 Alibaba 主页
        max_attempts = 6
        for attempt in range(max_attempts):
            try:
                await page.goto("https://www.alibaba.com", timeout=60000)
                await page.set_viewport_size({"width": 1920, "height": 1080})
                logging.info(await page.title())
                await page.wait_for_load_state("domcontentloaded", timeout=60000)
                if "Alibaba.com" in await page.title():
                    break
            except Exception as e:
                logging.error(f"Attempt to navigate to alibaba.com failed: {e}")
                if attempt == max_attempts - 1:
                    stop_browser(registration_info['containerCode'])
                    return f"Failed to navigate to alibaba.com: {e}"
                await asyncio.sleep(5)

        await accept_cookies(page)

        sign_in_element = await page.wait_for_selector('text=Sign in', timeout=20000)
        if not sign_in_element:
            stop_browser(registration_info['containerCode'])
            return "Waiting for 'Sign in' element timed out"
        parent_element = await sign_in_element.query_selector('xpath=..')

        # 悬停之前记录日志
        logging.info("准备悬停在 'Sign in' 元素上")

        # 悬停操作
        await parent_element.hover()

        # 设置随机悬停时间
        hover_time = random.uniform(1, 3)  # 设置悬停时间为1到3秒之间的随机值
        logging.info(f"已成功悬停在 'Sign in' 元素上，保持悬停 {hover_time:.2f} 秒")
        await asyncio.sleep(hover_time)

        logging.info("悬停结束，继续执行其他操作")

        # 监听'My Alibaba'弹窗
        async with page.expect_popup() as popup_info:
            my_alibaba_element = await page.wait_for_selector('a[href="https://i.alibaba.com/index.htm"]',
                                                              timeout=20000)
            if my_alibaba_element:
                await move_and_click(page, my_alibaba_element)
                logging.info("Clicked 'My Alibaba' element")
            else:
                logging.error("Could not find 'My Alibaba' element")
                stop_browser(registration_info['containerCode'])
                return "Could not find 'My Alibaba' element"

        alibaba_popup = await popup_info.value
        for i in range(3):  # 添加重试逻辑
            try:
                await alibaba_popup.wait_for_load_state("domcontentloaded", timeout=30000)
                break
            except PlaywrightTimeoutError:
                logging.error("Alibaba popup failed to load, retrying...")
                if i == 2:  # 最后一次重试还失败的话，终止流程
                    logging.error("Failed to load 'My Alibaba' popup after retries.")
                    stop_browser(registration_info['containerCode'])
                    return "Failed to load 'My Alibaba' popup"

        await accept_cookies(alibaba_popup)

        # 监听'Create account'弹窗
        async with alibaba_popup.expect_popup() as popup_info:
            create_account_element = await alibaba_popup.wait_for_selector('a[href*="reg/union_reg.htm"]',
                                                                           timeout=20000)
            if create_account_element:
                await move_and_click(alibaba_popup, create_account_element)
                logging.info("Clicked 'Create account' element")
            else:
                logging.error("Could not find 'Create account' element")
                stop_browser(registration_info['containerCode'])
                return "Could not find 'Create account' element"

        registration_popup = await popup_info.value
        for i in range(3):  # 添加重试逻辑
            try:
                await registration_popup.wait_for_load_state("networkidle", timeout=30000)
                break
            except PlaywrightTimeoutError:
                logging.error("Registration popup failed to load, retrying...")
                if i == 2:  # 最后一次重试还失败的话，终止流程
                    logging.error("Failed to load 'Create account' popup after retries.")
                    stop_browser(registration_info['containerCode'])
                    return "Failed to load 'Create account' popup"

        await registration_popup.wait_for_load_state("networkidle", timeout=60000)  # 等待注册页面加载到网络空闲状态

        # Ensure slider verification
        slider_verification_passed = False
        for _ in range(3):
            if await perform_slider_verification(registration_popup):
                slider_verification_passed = True
                break

        if not slider_verification_passed:
            logging.error("Slider verification failed after multiple attempts")
            stop_browser(registration_info['containerCode'])
            return "Slider verification failed after multiple attempts"

        logging.info("Navigated to registration page")

        await accept_cookies(registration_popup)  # 最后一次接受cookie弹窗

        # 确保所有必要的表单字段已经加载
        await registration_popup.wait_for_selector('input[name="email"]', timeout=10000)
        await registration_popup.wait_for_selector('input[name="password"]', timeout=10000)
        await registration_popup.wait_for_selector('input[name="confirmPassword"]', timeout=10000)
        await registration_popup.wait_for_selector('input[name="companyName"]', timeout=10000)
        await registration_popup.wait_for_selector('input[name="firstName"]', timeout=10000)
        await registration_popup.wait_for_selector('input[name="lastName"]', timeout=10000)
        await registration_popup.wait_for_selector('input[name="phoneNumber"]', timeout=10000)
        logging.info("所有表单元素加载完成")

        # 填写注册表单
        await fill_registration_form(registration_popup, registration_info)

        # 滑块验证尝试
        max_slider_attempts = 3
        slider_attempts = 0
        slider_verified = False
        while slider_attempts < max_slider_attempts:
            if await perform_slider_verification(registration_popup):
                logging.info("Slider verification passed")
                slider_verified = True
                break  # 滑块验证成功，跳出循环
            else:
                logging.info("Slider verification failed, retrying...")
                slider_attempts += 1
                await asyncio.sleep(random.uniform(2, 5))

        if not slider_verified:
            logging.error("Slider verification failed after multiple attempts")
            stop_browser(registration_info['containerCode'])  # 滑块验证失败时关闭浏览器
            return "Slider verification failed after multiple attempts"

        # 检查滑块验证通过后确认图标是否出现
        if await registration_popup.wait_for_selector('span.nc_iconfont.btn_ok', timeout=10000):
            logging.info("Slider verification confirmed")

            # 确认用户协议并点击注册按钮
            registration_result = await confirm_and_click_register_button(registration_popup)
            if registration_result != "Proceeding with registration":
                stop_browser(registration_info['containerCode'])
                return registration_result

            # 开始执行注册流程
            registration_result = await perform_registration_flow(registration_popup, registration_info, email_client)
            if registration_result == "注册成功":
                return "注册成功"
            else:
                logging.error(f"Registration failed: {registration_result}")
                stop_browser(registration_info['containerCode'])
                return f"Registration failed: {registration_result}"
    except Exception as e:
                logging.error(f"Browser operation error: {e}")
                stop_browser(registration_info['containerCode'])
                return f"Browser operation error: {e}"

# 填写注册表单
async def fill_registration_form(page, registration_info):
    form_fields = [
        ('input[name="email"]', registration_info['email']),
        ('input[name="password"]', registration_info['password']),
        ('input[name="confirmPassword"]', registration_info['confirm_password']),
        ('input[name="companyName"]', registration_info['company_name']),
        ('input[name="firstName"]', registration_info['first_name']),
        ('input[name="lastName"]', registration_info['last_name']),
        ('input[name="phoneNumber"]', registration_info['phone_number']),
        ('input[name="bizRole"][value="buyer"]', None)
    ]

    random.shuffle(form_fields)

    for selector, value in form_fields:
        field = await page.query_selector(selector)
        await move_and_click(page, field)
        if value:
            await type_like_human(page, field, value)
        else:
            await field.click()

        wait_time = random.uniform(0.5, 1)
        logging.info(f"等待 {wait_time:.2f} 秒后填写下一个字段")
        await asyncio.sleep(wait_time)

    await page.evaluate('window.scrollTo(0, 0)')

# 模拟人类打字
async def type_like_human(page, element, text):
    for char in text:
        await element.type(char, delay=random.uniform(0.1, 0.3))
    await asyncio.sleep(random.uniform(0.5, 2))


async def perform_registration_flow(page, registration_info, email_client):
    try:
        if await submit_registration_form(page, registration_info['email'], email_client):
            logging.info("Verification code submitted successfully")

            # 传递 registration_info 参数
            if await check_registration_success(page, registration_info):
                logging.info("Registration successful")
                update_env_remark(
                    registration_info['containerCode'],
                    f"注册完成, 账号: {registration_info['email']}, 密码: {registration_info['password']}"
                )

                # 等待页面加载完成再继续
                await page.wait_for_load_state('domcontentloaded', timeout=20000)

                await click_alibaba_link_with_gdpr(page)

                await perform_additional_actions(page, registration_info)

                return "注册成功"
            else:
                logging.error("Registration failed during 'My profile' check.")
                return "注册失败，未找到 'My profile' 元素"
        else:
            logging.error("Verification code submission failed.")
            return "注册失败，验证码提交失败"
    except Exception as e:
        logging.error(f"注册流程中发生异常: {e}")
        return f"注册失败，异常: {e}"


#提交验证码
async def submit_registration_form(page, email, email_client):
    code_input = await page.wait_for_selector('input[name="emailVerifyCode"]', timeout=60000)
    if code_input:
        logging.info("等待验证码...")

        max_attempts = 10
        attempt = 0
        verification_code = None

        while attempt < max_attempts and not verification_code:
            email_client.fetch_emails()
            verification_code = email_client.show_email_details(0)
            logging.info(f"获取到的验证码: {verification_code}")  # 增加日志输出

            if verification_code and verification_code.isdigit():
                break
            attempt += 1
            await asyncio.sleep(30)

        if verification_code and verification_code.isdigit():
            await type_like_human(page, code_input, verification_code)
            logging.info(f"验证码已输入: {verification_code}")  # 增加日志输出

            submit_code_button = await page.query_selector('button:has-text("Submit")')
            if submit_code_button:
                await move_and_click(page, submit_code_button)
                logging.info("已点击提交验证码按钮")  # 增加日志输出
                await asyncio.sleep(random.uniform(3, 5))  # 增加提交后的等待时间
                return True
            else:
                logging.info("未找到提交验证码按钮")
        else:
            logging.info("未能获取到有效的验证码")
    else:
        logging.info("验证码输入框未出现")
    return False



# 检查注册是否成功
# 更新后的检查注册是否成功函数
async def check_registration_success(page, registration_info, retries=3):
    for attempt in range(retries):
        try:
            # 查找 My Profile 元素
            element = await page.wait_for_selector(
                'a[href="//profile.alibaba.com/profile/my_profile.htm?tracelog=buyerMaHome"]',
                timeout=60000
            )
            if element:
                attributes = await element.get_property('outerHTML')
                logging.info(f"找到 'My profile' 元素，注册成功，元素属性: {attributes}")
                return True  # 找到目标元素，返回 True 表示注册成功
            else:
                logging.error(f"未找到 'My profile' 元素，重试第 {attempt + 1}/{retries}")

        except PlaywrightTimeoutError:
            logging.error(f"超时未找到 'My profile' 元素，重试第 {attempt + 1}/{retries}")

        # 如果超时未找到元素，执行以下操作
        try:
            logging.info("刷新当前页面...")
            await page.reload()
            await page.wait_for_load_state('domcontentloaded', timeout=60000)

            # 检查是否跳转到登录页面
            if "login.alibaba.com" in page.url:
                logging.info("页面跳转到登录页面，准备重新登录")
                await handle_login(page, registration_info)  # 执行登录逻辑
                await page.wait_for_load_state('domcontentloaded', timeout=60000)  # 等待登录后的页面加载

            # 再次检查 My Profile 元素
            element = await page.query_selector('a[href="//profile.alibaba.com/profile/my_profile.htm?tracelog=buyerMaHome"]')
            if element:
                logging.info(f"在刷新后找到 'My profile' 元素，继续后续操作")
                return True  # 找到目标元素，返回 True 表示注册成功
            else:
                logging.info("未找到 'My profile' 元素，准备进行下一次尝试...")

        except PlaywrightTimeoutError:
            logging.error(f"刷新页面时发生超时错误，重试第 {attempt + 1}/{retries}")
        except Exception as e:
            logging.error(f"刷新页面时发生错误: {e}")

        # 重试等待时间
        await asyncio.sleep(5)

    logging.error("多次尝试后仍未找到 'My profile' 元素，注册失败")
    return False  # 如果多次尝试都失败，则返回 False



# 生成随机注册信息
def generate_random_info(token, container_code, group_pay_id):
    url = "http://121.199.27.26:5000/generate"
    payload = {
        "token": token,
        "group_pay_id": group_pay_id,
        "count": 1
    }

    try:
        response = session.post(url, json=payload)
        response.raise_for_status()
        response_data = response.json()
        if 'result' in response_data and response_data['result']:
            valid_emails = [item for item in response_data['result'] if '----' in item]
            if not valid_emails:
                raise ValueError("No valid email data found in API response")

            email_info = valid_emails[0]
            email_account, password = email_info.split('----', 1)
            return {
                "email": email_account,
                "password": password,
                "confirm_password": password,
                "company_name": re.sub(r'\W+', '', Faker().company()),
                "first_name": Faker().first_name(),
                "last_name": Faker().last_name(),
                "phone_number": Faker().msisdn()[:10],
                "containerCode": container_code
            }
        else:
            raise ValueError("API response missing 'result' or result list is empty")
    except requests.exceptions.RequestException as e:
        raise Exception(f"API请求失败: {e}")

# 更新环境备注信息
def update_env_remark(container_id, remark):
    env_list = get_environment_list(container_id)

    logging.info("获取的环境列表: %s", env_list)

    if not env_list or env_list.get('code') != 0 or 'data' not in env_list:
        logging.error("未找到指定的环境信息或获取环境信息失败")
        return

    env_info = env_list['data']['list'][0]

    url = r'http://127.0.0.1:6873/api/v1/env/update'
    headers = {
        'Content-Type': 'application/json'
    }
    payload = {
        "containerCode": container_id,
        "containerName": env_info.get('containerName', ''),
        "remark": remark,
        "tagName": env_info.get('tagName', ''),
        "coreVersion": env_info.get('coreVersion', 100),
        "videoThrottle": env_info.get('videoThrottle', 0),
        "imgThrottle": env_info.get('imgThrottle', 0),
        "imgThrottleSize": env_info.get('imgThrottleSize', 0)
    }

    logging.info(f"准备发送更新请求，payload: {json.dumps(payload)}")

    try:
        response = session.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        try:
            response_data = response.json()
            if response_data.get('code') == 0:
                logging.info("环境备注信息更新成功")
                return remark  # 返回更新后的备注信息
            else:
                logging.error(f"环境备注信息更新失败，错误代码: {response_data.get('code')}, 错误信息: {response_data.get('message')}")
        except ValueError as e:
            logging.error(f"JSON解析错误: {e}")
    except requests.exceptions.RequestException as e:
        logging.error(f"更新环境备注信息请求失败: {e}")


browser_stopped = {}  # 使用字典来存储每个 container_code 的停止状态

def stop_browser_once(container_code, use_post=True):
    global browser_stopped
    if browser_stopped.get(container_code, False):
        logging.info(f"浏览器环境 {container_code} 已关闭，跳过多余的关闭操作。")
        return

    try:
        logging.info(f"准备停止环境，环境ID: {container_code}")

        # 根据是否使用POST选择不同的请求方式
        if use_post:
            url = 'http://localhost:6873/api/v1/browser/stop'
            data = {"containerCode": container_code}
            logging.info(f"发送POST请求关闭环境，URL: {url}, 环境ID: {container_code}, 数据: {data}")
            response = session.post(url, json=data)
        else:
            url = f'http://localhost:6873/api/v1/browser/stop?containerCode={container_code}'
            logging.info(f"发送GET请求关闭环境，URL: {url}")
            response = session.get(url)

        # 记录状态码和响应内容
        logging.info(f"停止环境请求已发送，状态码: {response.status_code}, 响应内容: {response.text}")

        if response.status_code == 200:
            response_json = response.json()
            logging.info(f"停止环境的响应: {response_json}")

            # 检查返回的 code 和 statusCode 是否为 0 来确认停止成功
            if str(response_json.get('code')) == '0' and str(response_json['data'].get('statusCode')) == '0':
                logging.info(f"环境 {container_code} 已成功关闭")
                browser_stopped[container_code] = True  # 设置标志位，表示环境已停止
            else:
                logging.error(f"停止环境失败，错误代码: {response_json.get('code')}, 信息: {response_json.get('msg')}")
        else:
            logging.error(f"停止环境请求失败，返回码: {response.status_code}, 信息: {response.text}")
    except Exception as e:
        logging.error(f"停止环境时出错: {str(e)}")




# 捕获异常并返回注册失败信息
# 捕获异常并返回注册失败信息
async def perform_registration_flow_V2(page, registration_info, email_client):
    try:
        # 提交验证码
        if await submit_registration_form(page, registration_info['email'], email_client):
            logging.info("Verification code submitted successfully")

            # 检查注册是否成功
            if await check_registration_success(page, registration_info):
                logging.info("Registration successful")

                # 更新备注信息并执行后续操作
                try:
                    update_env_remark(
                        registration_info['containerCode'],
                        f"注册完成, 账号: {registration_info['email']}, 密码: {registration_info['password']}"
                    )
                    await page.wait_for_load_state('domcontentloaded', timeout=60000)

                    # 点击阿里巴巴链接，处理 GDPR 弹窗
                    await click_alibaba_link_with_gdpr(page)

                    # 执行额外的操作
                    await perform_additional_actions(page, registration_info)

                    return "注册成功"

                # 捕获更新备注和后续操作时的异常
                except Exception as e:
                    logging.error(f"注册成功后发生异常: {e}")
                    return f"注册失败，异常: {e}"

            # 检查 'My profile' 失败
            else:
                logging.error("Registration failed during 'My profile' check.")
                return "注册失败，未找到 'My profile' 元素"

        # 验证码提交失败
        else:
            logging.error("Verification code submission failed.")
            return "注册失败，验证码提交失败"

    # 捕获整个注册流程中的异常
    except Exception as e:
        logging.error(f"注册流程中发生异常: {e}")
        return f"注册失败，异常: {e}"


# 修改后的点击 Alibaba.com 链接逻辑，带有 GDPR 弹窗监听

async def click_alibaba_link_with_gdpr(page, retries=3, timeout=60000):
    async def monitor_gdpr_popup(page, check_interval=1, max_duration=15):
        total_wait_time = 0
        while total_wait_time < max_duration:
            try:
                gdpr_notice = await page.query_selector('div.GDPR-cookies-notice')
                if gdpr_notice:
                    logging.info("发现GDPR通知，点击同意按钮")
                    agree_button = await page.query_selector('div.gdpr-btn.gdpr-agree-btn')
                    if agree_button:
                        await move_and_click(page, agree_button)
                        await asyncio.sleep(2)
                        logging.info("GDPR同意按钮已点击")
                    break
            except PlaywrightTimeoutError:
                pass
            await asyncio.sleep(check_interval)
            total_wait_time += check_interval

        if total_wait_time >= max_duration:
            logging.info("达到最大等待时间，未检测到GDPR弹窗")

    # 创建监听任务
    gdpr_task = asyncio.create_task(monitor_gdpr_popup(page))

    for attempt in range(retries):
        try:
            # 延长查找元素的时间
            alibaba_link = await page.wait_for_selector('a[href="//www.alibaba.com?tracelog=ma_oversea_top_alibaba"]', timeout=timeout)
            if alibaba_link:
                await gdpr_task  # 等待GDPR任务完成
                await alibaba_link.hover()
                await asyncio.sleep(random.uniform(0.5, 2))
                await alibaba_link.click()

                # 等待页面导航完成
                await page.wait_for_load_state('domcontentloaded', timeout=timeout)

                logging.info("Clicked Alibaba.com link to go to the homepage")
                await asyncio.sleep(20)
                return True  # 如果成功点击，不再进行后续重试
            else:
                logging.error(f"Failed to find and click the Alibaba.com link on attempt {attempt + 1}/{retries}")
        except PlaywrightTimeoutError:
            logging.error("检测元素时发生超时错误")
        except Exception as e:
            logging.error(f"在检测或点击Alibaba链接时发生错误: {e}")

        # 如果重试次数未达到上限，等待一段时间后重试
        if attempt < retries - 1:
            await asyncio.sleep(5)

    # 如果所有重试都失败，抛出异常以终止流程
    raise Exception("Failed to find and click Alibaba.com link after multiple attempts.")




# 定义全局的锁对象
stop_browser_lock = threading.Lock()

# 简化的停止浏览器函数，无需重试机制
def stop_browser(container_code, use_post=True):
    global browser_stopped
    try:
        # 使用锁来避免多线程环境下重复调用
        with stop_browser_lock:
            # 检查浏览器是否已经停止
            if browser_stopped.get(container_code, False):
                logging.info(f"环境 {container_code} 已关闭，跳过多余的关闭操作。")
                return

            logging.info(f"准备停止环境，环境ID: {container_code}")

            # 根据是否使用POST选择不同的请求方式
            if use_post:
                url = 'http://localhost:6873/api/v1/browser/stop'
                data = {"containerCode": container_code}
                logging.info(f"发送POST请求关闭环境，URL: {url}, 环境ID: {container_code}, 数据: {data}")
                response = session.post(url, json=data)
            else:
                url = f'http://localhost:6873/api/v1/browser/stop?containerCode={container_code}'
                logging.info(f"发送GET请求关闭环境，URL: {url}")
                response = session.get(url)

            # 记录状态码和响应内容
            logging.info(f"停止环境请求已发送，状态码: {response.status_code}, 响应内容: {response.text}")

            if response.status_code == 200:
                response_json = response.json()
                logging.info(f"停止环境的响应: {response_json}")

                # 检查返回的 code 和 statusCode 是否为 0 来确认停止成功
                if str(response_json.get('code')) == '0' and str(response_json['data'].get('statusCode')) == '0':
                    logging.info(f"环境 {container_code} 已成功关闭")
                    # 设置标志位，表示该 container_code 的环境已停止
                    browser_stopped[container_code] = True
                else:
                    logging.error(f"停止环境失败，错误代码: {response_json.get('code')}, 信息: {response_json.get('msg')}")
            else:
                logging.error(f"停止环境请求失败，返回码: {response.status_code}, 信息: {response.text}")
    except Exception as e:
        logging.error(f"停止环境时出错: {str(e)}")




# 提交处理
import re

# 提取 containerCode 的函数
def extract_container_code(input_text):
    match = re.search(r'containerCode:\s*(\d+)', input_text)
    if match:
        return match.group(1)
    return None

# 修改后的 on_submit 函数
def on_submit():
    token = "c699a6fc1add4bb2a965dac58a88d11e"
    group_pay_id = "1723045055121098052"

    input_text = input_textbox.get("1.0", END).strip()
    input_lines = input_text.split("\n")
    container_codes = []

    for line in input_lines:
        code = extract_container_code(line)
        if code:
            container_codes.append(code)

    max_workers = int(thread_count_var.get())

    async def main_executor():
        loop = asyncio.get_event_loop()
        semaphore = asyncio.Semaphore(max_workers)

        async def limited_process_registration(container_code):
            async with semaphore:
                try:
                    result = await process_registration(token, container_code, group_pay_id)
                    return f"{container_code}: {result}"
                except Exception as e:
                    logging.error(f"注册失败，container_code: {container_code}, 错误: {e}")
                    return f"{container_code}: 注册失败，错误: {str(e)}"

        tasks = []
        for container_code in container_codes:
            if container_code.strip():
                tasks.append(loop.create_task(limited_process_registration(container_code)))

        for task in asyncio.as_completed(tasks):
            try:
                result = await task
                result_textbox.insert(END, result + "\n")  # 显示结果
                result_textbox.see(END)
                logging.info(f"注册结果: {result}")
            except Exception as e:
                logging.error(f"线程执行出错: {e}")
                result_textbox.insert(END, f"线程执行出错: {e}\n")
                result_textbox.see(END)

    asyncio.run(main_executor())



# 处理注册任务
async def process_registration(token, container_code, group_pay_id):
    container_name, container_code = get_container_info(container_code)
    container_name_var.set(container_name)
    container_code_var.set(container_code)
    configure_logging()

    logging.info(f"开始处理注册, containerName: {container_name_var.get()}, containerCode: {container_code_var.get()}")

    browser_context = None  # 初始化 browser_context 为 None
    playwright = None  # 初始化 playwright 为 None
    registration_result = None  # 初始化注册结果

    try:
        registration_info = generate_random_info(token, container_code, group_pay_id)
    except Exception as e:
        logging.error(f"生成邮箱失败: {e}")
        registration_result = f"注册失败，生成邮箱失败: {e}"  # 确保失败时返回注册失败
        return registration_result

    logging.info(f"生成的注册信息: {registration_info}")

    email_address = registration_info["email"]
    email_password = registration_info["password"]
    email_client = EmailClient(email_address, email_password)

    try:
        # 启动浏览器环境的 API 请求
        url = r'http://127.0.0.1:6873/api/v1/browser/start'
        open_data = {
            "containerCode": container_code,
            "args": ['--start-maximized', '--disable-extensions']  # 在这里加入浏览器的启动参数
        }
        response = session.post(url, json=open_data)
        response.raise_for_status()
        open_res = response.json()

        if open_res['code'] != 0:
            logging.error(f"环境打开失败: {open_res}")
            registration_result = f"注册失败，环境打开失败: {open_res}"
            return registration_result

        debugging_port = open_res['data']['debuggingPort']
        playwright = await async_playwright().start()
        browser_context = await get_browser_context(playwright, debugging_port)

        result = await open_alibaba(browser_context, registration_info, email_client)
        if "注册失败" in result:  # 在此处根据返回值检查失败情况
            logging.error(f"{email_address}, {result}")
            registration_result = f"注册失败，错误: {result}"  # 确保返回的是注册失败
            return registration_result
        else:
            registration_result = f"{email_address}, 注册成功"  # 只有成功时返回注册成功

    except Exception as e:
        logging.error(f"浏览器操作出错: {e}")
        registration_result = f"注册失败，浏览器操作出错: {e}"  # 捕获所有异常并返回注册失败


    finally:

        try:

            if browser_context:  # 检查 browser_context 是否已定义

                await browser_context.close()

                logging.info("浏览器上下文已关闭")

        except Exception as e:

            logging.error(f"关闭浏览器上下文出错: {e}")

        if playwright:  # 确保 playwright 正常关闭

            if browser_context and browser_context.browser:
                await browser_context.browser.close()  # 确保关闭整个浏览器实例

                logging.info("浏览器已关闭")

            await playwright.stop()

            logging.info("Playwright 已停止")

        # 在浏览器关闭后调用 stop_browser 函数

        stop_browser(container_code)  # 添加这行确保环境被停止

        logging.info(f"完成处理注册: {email_address}, 容器代码: {container_code}")

    # 如果注册结果未被设置，则默认返回注册失败
    if registration_result is None:
        registration_result = f"{email_address}, 注册失败"

    return registration_result




# 主函数，启动GUI
def main():
    global input_textbox, thread_count_var, result_textbox

    root = Tk()
    root.title("Batch Registration Input")

    Label(root, text="批量输入 (格式: container_code，每行一个)").pack()

    input_textbox = ScrolledText(root, width=60, height=10)
    input_textbox.pack()

    Label(root, text="线程数").pack()
    thread_count_var = StringVar(value="2")
    thread_count_entry = Entry(root, textvariable=thread_count_var)
    thread_count_entry.pack()

    Button(root, text="Submit", command=on_submit).pack(pady=10)

    Label(root, text="注册结果").pack()
    result_textbox = ScrolledText(root, width=60, height=10)
    result_textbox.pack()

    root.mainloop()

if __name__ == '__main__':
    main()