"""
测试比特浏览器打开并登录谷歌功能
"""
import sys
import os
import asyncio

# 添加src到路径
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from core.bit_api import openBrowser, get_browser_info
from core.bit_playwright import google_login
from playwright.async_api import async_playwright


async def test_google_login_for_browser(browser_id: str):
    """
    测试指定浏览器窗口ID的谷歌登录功能
    """
    print(f"\n{'='*60}")
    print(f"测试窗口ID: {browser_id}")
    print(f"{'='*60}\n")
    
    # 1. 获取浏览器信息
    print("[1/4] 获取浏览器信息...")
    browser_info = get_browser_info(browser_id)
    if not browser_info:
        print(f"❌ 找不到窗口ID: {browser_id}")
        return False
    
    print(f"  窗口名称: {browser_info.get('name', 'N/A')}")
    
    # 2. 解析账号信息
    print("\n[2/4] 解析账号信息...")
    remark = browser_info.get('remark', '')
    parts = remark.split('----')
    
    account_info = {
        'email': parts[0].strip() if len(parts) > 0 else '',
        'password': parts[1].strip() if len(parts) > 1 else '',
        'backup_email': parts[2].strip() if len(parts) > 2 else '',
        'secret': parts[3].strip() if len(parts) > 3 else ''
    }
    
    print(f"  邮箱: {account_info['email']}")
    print(f"  密码: {'*' * len(account_info['password'])}")
    print(f"  辅助邮箱: {account_info['backup_email']}")
    print(f"  2FA秘钥: {'已设置' if account_info['secret'] else '未设置'}")
    
    if not account_info['email']:
        print("❌ 未找到邮箱信息")
        return False
    
    # 3. 打开浏览器窗口
    print("\n[3/4] 打开浏览器窗口...")
    result = openBrowser(browser_id)
    if not result.get('success'):
        print(f"❌ 打开窗口失败: {result.get('msg')}")
        return False
    
    ws_url = result['data']['ws']
    print(f"  ✅ 窗口已打开")
    print(f"  WebSocket: {ws_url[:50]}...")
    
    # 4. 使用Playwright连接并登录Google
    print("\n[4/4] 连接Playwright并登录谷歌...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(ws_url)
            
            # 获取第一个上下文和页面
            contexts = browser.contexts
            if not contexts:
                print("❌ 未找到浏览器上下文")
                return False
            
            context = contexts[0]
            pages = context.pages
            
            if not pages:
                print("  创建新页面...")
                page = await context.new_page()
            else:
                page = pages[0]
            
            print(f"  当前页面URL: {page.url}")
            
            # 执行谷歌登录
            print("\n  开始谷歌登录流程...")
            print("-" * 60)
            await google_login(page, account_info)
            print("-" * 60)
            
            await asyncio.sleep(3)
            print(f"\n  登录后页面URL: {page.url}")
            
            if "myaccount.google.com" in page.url or "one.google.com" in page.url:
                print("\n  ✅ 登录成功！")
                return True
            else:
                print(f"\n  ⚠️ 登录可能未完成，当前URL: {page.url}")
                print("  请手动检查浏览器窗口")
                return None
                
    except Exception as e:
        print(f"\n❌ Playwright连接失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """
    主测试函数
    """
    test_browsers = [
        "819d662e03724b119868e8954b2fc47b",
        "0b2a0fe76df34c51948de65e4630de9d"
    ]
    
    print("\n" + "="*60)
    print("比特浏览器谷歌登录功能测试")
    print("="*60)
    
    results = {}
    
    for browser_id in test_browsers:
        try:
            result = await test_google_login_for_browser(browser_id)
            results[browser_id] = result
        except Exception as e:
            print(f"\n❌ 测试出错: {e}")
            import traceback
            traceback.print_exc()
            results[browser_id] = False
        
        print("\n" + "="*60)
        await asyncio.sleep(2)
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    for browser_id, result in results.items():
        status = "✅ 成功" if result is True else ("⚠️ 待确认" if result is None else "❌ 失败")
        print(f"{browser_id}: {status}")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
