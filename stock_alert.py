import akshare as ak
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import time
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.header import Header
import warnings
import concurrent.futures
import threading

# ===================== 【核心自定义参数】=====================
# 股票配置列表
STOCK_CONFIGS = [
    {
        'name': '长城汽车',
        'code': '601633',
        'alert_type': 'golden_cross',  # 金叉预警
        'ma_short': 10,   # 短期均线（10日）
        'ma_long': 20     # 长期均线（20日）
    },
    {
        'name': '大秦铁路',
        'code': '601006',
        'alert_type': 'three_above_ma',  # 连续三根k线站上20日均线预警
        'ma_line': 20     # 均线参数（20日）
    },
    {
        'name': '同仁堂',
        'code': '600085',
        'alert_type': 'golden_cross',  # 金叉预警
        'ma_short': 10,   # 短期均线（10日）
        'ma_long': 20     # 长期均线（20日）
    },
    {
        'name': '中国移动',
        'code': '600941',
        'alert_type': 'three_above_ma',  # 连续三根k线站上20日均线预警
        'ma_line': 20     # 均线参数（20日）
    },
    {
        'name': '中国联通',
        'code': '600050',
        'alert_type': 'three_above_ma',  # 连续三根k线站上20日均线预警
        'ma_line': 20     # 均线参数（20日）
    },
    {
        'name': '中国电信',
        'code': '601728',
        'alert_type': 'three_above_ma',  # 连续三根k线站上20日均线预警
        'ma_line': 20     # 均线参数（20日）
    }
]

# 数据参数
DATA_START_DATE = "20240101"  # 数据起始日期
DATA_END_DATE = datetime.now().strftime("%Y%m%d")  # 自动获取当前日期

# 【邮件配置】
# 在GitHub Actions中，建议使用环境变量存储敏感信息
EMAIL_CONFIG = {
    "sender": os.environ.get("EMAIL_SENDER", "3754906614@qq.com"),       # 发件邮箱
    "receiver": os.environ.get("EMAIL_RECEIVER", "3754906614@qq.com"),       # 收件邮箱
    "smtp_server": os.environ.get("EMAIL_SMTP_SERVER", "smtp.qq.com"),         # SMTP服务器
    "smtp_port": int(os.environ.get("EMAIL_SMTP_PORT", "465")),                     # SSL端口
    "auth_code": os.environ.get("EMAIL_AUTH_CODE", "oeoockwbswpndbgf")         # 授权码
}

# ===================== 基础配置 =====================
# 过滤无关警告
warnings.filterwarnings("ignore", category=UserWarning, module="py_mini_racer")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pkg_resources")

# 配置matplotlib在无图形界面环境下运行
import matplotlib
matplotlib.use('Agg')  # 非交互式后端

# 设置matplotlib中文显示
import platform
import matplotlib.font_manager as fm
import matplotlib

# 在Linux环境中（GitHub Actions），确保使用支持中文的字体
if platform.system() == 'Linux':
    # 对于GitHub Actions的Ubuntu环境，使用DejaVu Sans字体，它支持基本的中文字符
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "WenQuanYi Micro Hei", "Heiti TC"]
    plt.rcParams["font.family"] = "sans-serif"
elif platform.system() == 'Windows':
    windows_fonts = ['SimHei', 'Microsoft YaHei', 'SimSun', 'FangSong']
    available_fonts = []
    for font in fm.fontManager.ttflist:
        if font.name in windows_fonts:
            available_fonts.append(font.name)
    
    if available_fonts:
        plt.rcParams["font.sans-serif"] = [available_fonts[0]]
        plt.rcParams["font.family"] = "sans-serif"
    else:
        plt.rcParams["font.sans-serif"] = ["SimHei"]
        warnings.filterwarnings("ignore", category=UserWarning, message="Glyph.*missing from font")
else:
    # 其他系统
    plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "WenQuanYi Micro Hei", "Heiti TC"]
    plt.rcParams["font.family"] = "sans-serif"

plt.rcParams["axes.unicode_minus"] = False  # 解决负号显示问题
# 强制使用UTF-8编码
matplotlib.rcParams['font.family'] = 'sans-serif'
matplotlib.rcParams['font.sans-serif'] = ['DejaVu Sans', 'SimHei', 'WenQuanYi Micro Hei']
matplotlib.rcParams['axes.unicode_minus'] = False

# 定义保存HTML输出的文件夹
ALERT_OUTPUT_DIR = os.environ.get('ALERT_OUTPUT_DIR', os.path.join(os.getcwd(), 'alert_output'))

# 定义当天日期的文件夹
TODAY_DATE = datetime.now().strftime('%Y%m%d')
TODAY_DIR = os.path.join(ALERT_OUTPUT_DIR, TODAY_DATE)
if not os.path.exists(TODAY_DIR):
    os.makedirs(TODAY_DIR)

# 定义保存图片的文件夹（当天日期文件夹的子文件夹）
PICTURE_DIR = os.path.join(TODAY_DIR, 'picture')
if not os.path.exists(PICTURE_DIR):
    os.makedirs(PICTURE_DIR)
    print(f"✅ 创建图片保存目录：{PICTURE_DIR}")
else:
    print(f"📁 图片保存目录已存在：{PICTURE_DIR}")

# ===================== 数据获取函数 =====================
def safe_get_data(func, *args, **kwargs):
    """安全获取数据，带重试机制"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            if result is not None and not result.empty:
                return result
            time.sleep(2)
        except Exception as e:
            print(f"  第{attempt+1}次尝试失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
            else:
                print(f"  所有尝试都失败了")
    return None

def get_stock_data(stock_code: str, stock_name: str) -> pd.DataFrame:
    """获取股票历史数据，使用多种数据源作为备用，带重试机制"""
    print(f"📥 正在获取{stock_name}({stock_code})历史数据...")
    
    try:
        # 定义akshare的多种数据源获取函数，优先使用腾讯数据源
        ak_sources = [
            ("腾讯", ak.stock_zh_a_hist_tx),  # 腾讯数据源，需要带市场前缀
            ("东方财富", ak.stock_zh_a_hist),   # 东财数据源，支持纯数字代码
        ]
        
        for source_name, source_func in ak_sources:
            try:
                print(f"  尝试数据源: {source_name}")
                
                # 根据数据源调整参数
                call_params = {
                    'start_date': DATA_START_DATE,
                    'end_date': DATA_END_DATE,
                    'adjust': 'qfq'  # 前复权
                }
                
                # 调整股票代码格式和参数
                symbol = stock_code
                if source_name == "腾讯":
                    # 腾讯数据源需要市场前缀，并且不接受period参数
                    if len(stock_code) == 6:
                        if stock_code.startswith('6'):
                            symbol = f'sh{stock_code}'
                        else:
                            symbol = f'sz{stock_code}'
                else:
                    # 默认数据源(东财)支持纯数字代码，需要period参数
                    call_params['period'] = 'daily'
                
                call_params['symbol'] = symbol
                
                # 使用带重试机制的安全数据获取
                df = safe_get_data(source_func, **call_params)
                
                if df is not None and not df.empty:
                    print(f"  ✅ {source_name}数据源获取{stock_name}({stock_code})数据成功，共{len(df)}条")
                    
                    # 重命名列（处理不同数据源的列名差异）
                    column_mapping = {
                        # 中文列名（东方财富）
                        "日期": "date",
                        "开盘": "open",
                        "最高": "high",
                        "最低": "low",
                        "收盘": "close",
                        "成交量": "volume",
                        "成交额": "amount",
                        # 英文列名（腾讯或其他数据源）
                        "date": "date",
                        "open": "open",
                        "high": "high",
                        "low": "low",
                        "close": "close",
                        "volume": "volume",
                        "amount": "amount",
                        "vol": "volume",  # 腾讯数据源可能使用vol表示成交量
                        "turnover": "amount"  # 腾讯数据源可能使用turnover表示成交额
                    }
                    
                    # 只重命名存在的列
                    rename_dict = {}
                    for old_col, new_col in column_mapping.items():
                        if old_col in df.columns:
                            rename_dict[old_col] = new_col
                    
                    if rename_dict:
                        df.rename(columns=rename_dict, inplace=True)
                    
                    # 打印当前数据框的列名，方便调试
                    print(f"  📋 {source_name}数据源返回的列名: {list(df.columns)}")
                    
                    # 确保必要的列存在
                    required_columns = ["date", "open", "high", "low", "close"]
                    # 成交量和成交额是可选的，如果缺少则设置为0
                    optional_columns = ["volume", "amount"]
                    
                    if all(col in df.columns for col in required_columns):
                        # 如果缺少成交量或成交额，设置为0
                        for col in optional_columns:
                            if col not in df.columns:
                                df[col] = 0
                                print(f"  ⚠️  缺少{col}列，已设置为0")
                        
                        # 数据清洗
                        df["date"] = pd.to_datetime(df["date"])
                        df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
                        
                        print(f"  ✅ {source_name}数据源数据格式检查通过，共{len(df)}条数据")
                        return df
                    else:
                        missing_cols = [col for col in required_columns if col not in df.columns]
                        print(f"  ❌ {source_name}数据源数据格式不符合要求，缺少必要列: {missing_cols}")
                        continue
            except Exception as e:
                print(f"  ❌ {source_name}数据源获取失败：{e}")
                continue
        
        # 尝试不同复权方式作为备用
        print("  尝试备用方案：不同复权方式")
        adjust_methods = [
            ("不复权", ""),
            ("后复权", "hfq")
        ]
        
        for adjust_name, adjust_method in adjust_methods:
            try:
                print(f"    尝试{adjust_name}")
                df = safe_get_data(ak.stock_zh_a_hist,
                                 symbol=stock_code,
                                 period="daily",
                                 start_date=DATA_START_DATE,
                                 end_date=DATA_END_DATE,
                                 adjust=adjust_method)
                
                if df is not None and not df.empty:
                    # 重命名列
                    df.rename(columns={
                        "日期": "date",
                        "开盘": "open",
                        "最高": "high",
                        "最低": "low",
                        "收盘": "close",
                        "成交量": "volume",
                        "成交额": "amount"
                    }, inplace=True)
                    
                    # 确保必要的列存在
                    required_columns = ["date", "open", "high", "low", "close", "volume", "amount"]
                    if all(col in df.columns for col in required_columns):
                        # 数据清洗
                        df["date"] = pd.to_datetime(df["date"])
                        df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
                        
                        print(f"  ✅ {adjust_name}数据获取成功，共{len(df)}条")
                        return df
            except Exception as e:
                print(f"    ❌ {adjust_name}获取失败：{e}")
                continue
        
        # 所有数据源都失败
        print(f"❌ 所有数据源都失败，未获取到{stock_name}({stock_code})的数据")
        return pd.DataFrame()
        
    except Exception as e:
        print(f"❌ 获取{stock_name}({stock_code})数据时发生错误：{e}")
        return pd.DataFrame()

# ===================== 均线计算和预警判断 =====================
def calculate_ma_and_check_alert(df: pd.DataFrame, stock_config: dict) -> dict:
    """计算均线并检查预警信号"""
    if df.empty:
        return {
            'has_alert': False,
            'alert_type': None,
            'latest_data': None,
            'df': pd.DataFrame()
        }
    
    df = df.copy()
    stock_name = stock_config['name']
    alert_type = stock_config['alert_type']
    
    if alert_type == 'golden_cross':
        # 金叉预警逻辑
        ma_short = stock_config['ma_short']
        ma_long = stock_config['ma_long']
        
        # 计算均线
        df[f'ma{ma_short}'] = df['close'].rolling(window=ma_short).mean()
        df[f'ma{ma_long}'] = df['close'].rolling(window=ma_long).mean()
        
        # 计算均线差值
        df['ma_diff'] = df[f'ma{ma_short}'] - df[f'ma{ma_long}']
        
        # 检查上穿信号（金叉）
        # 条件：昨天 ma_short < ma_long，今天 ma_short > ma_long
        df['golden_cross'] = (df['ma_diff'].shift(1) <= 0) & (df['ma_diff'] > 0)
        
        # 获取最新数据
        latest_row = df.iloc[-1]
        
        # 检查是否有预警信号
        has_alert = latest_row['golden_cross']
        alert_name = '金叉预警' if has_alert else None
        
        latest_data = {
            'date': latest_row['date'].strftime('%Y-%m-%d'),
            'close': latest_row['close'],
            f'ma{ma_short}': latest_row[f'ma{ma_short}'],
            f'ma{ma_long}': latest_row[f'ma{ma_long}'],
            'ma_diff': latest_row['ma_diff']
        }
        
    elif alert_type == 'three_above_ma':
        # 连续三根k线站上20日均线预警逻辑
        ma_line = stock_config['ma_line']
        
        # 计算均线
        df[f'ma{ma_line}'] = df['close'].rolling(window=ma_line).mean()
        
        # 检查收盘价是否站在均线上方
        df['above_ma'] = df['close'] > df[f'ma{ma_line}']
        
        # 检查连续三根k线站上均线
        # 使用rolling窗口计算连续为True的天数
        df['consecutive_above_ma'] = df['above_ma'].rolling(window=3).sum()
        
        # 连续三根都站在均线上方
        df['three_above_ma'] = df['consecutive_above_ma'] == 3
        
        # 检查是否是第一次出现连续三根（前一天不是连续三根）
        df['first_three_above_ma'] = False
        if len(df) > 1:
            df['first_three_above_ma'] = df['three_above_ma'] & (~df['three_above_ma'].shift(1).fillna(False))
        
        # 获取最新数据
        latest_row = df.iloc[-1]
        
        # 检查是否有预警信号（只在第一次出现连续三根时触发）
        has_alert = latest_row['first_three_above_ma']
        alert_name = '连续三根k线站上20日均线预警' if has_alert else None
        
        latest_data = {
            'date': latest_row['date'].strftime('%Y-%m-%d'),
            'close': latest_row['close'],
            f'ma{ma_line}': latest_row[f'ma{ma_line}'],
            'consecutive_above_ma': int(latest_row['consecutive_above_ma'])
        }
    
    elif alert_type == 'three_carriers_above_ma':
        # 三个运营商都站在20日均线上方预警逻辑
        ma_line = stock_config['ma_line']
        carriers = stock_config['carriers']
        
        # 存储三个运营商的数据
        carriers_data = []
        all_above_ma = True
        
        # 对每个运营商获取数据并检查
        for carrier in carriers:
            carrier_name = carrier['name']
            carrier_code = carrier['code']
            
            # 获取运营商股票数据
            carrier_df = get_stock_data(carrier_code, carrier_name)
            
            if carrier_df.empty:
                print(f"❌ 未获取到{carrier_name}数据")
                all_above_ma = False
                break
            
            # 计算20日均线
            carrier_df[f'ma{ma_line}'] = carrier_df['close'].rolling(window=ma_line).mean()
            
            # 获取最新数据
            latest_carrier_row = carrier_df.iloc[-1]
            latest_close = latest_carrier_row['close']
            latest_ma = latest_carrier_row[f'ma{ma_line}']
            above_ma = latest_close > latest_ma
            
            # 存储数据
            carriers_data.append({
                'name': carrier_name,
                'code': carrier_code,
                'close': latest_close,
                f'ma{ma_line}': latest_ma,
                'above_ma': above_ma
            })
            
            # 检查是否站在均线上方
            if not above_ma:
                all_above_ma = False
        
        # 检查是否有预警信号
        has_alert = all_above_ma and len(carriers_data) == 3
        alert_name = '三大运营商都站在20日均线上方预警' if has_alert else None
        
        # 获取最新日期
        latest_date = datetime.now().strftime('%Y-%m-%d')
        if carriers_data:
            latest_date = carriers_data[0]['close'].name.strftime('%Y-%m-%d') if hasattr(carriers_data[0]['close'], 'name') else latest_date
        
        # 构建最新数据
        latest_data = {
            'date': latest_date,
            'carriers': carriers_data
        }
        
        # 构建df（仅用于图表）
        df = pd.DataFrame()
    
    return {
        'has_alert': has_alert,
        'alert_type': alert_name,
        'latest_data': latest_data,
        'df': df
    }

# ===================== 绘制预警图表 =====================
def plot_alert_chart(df: pd.DataFrame, stock_config: dict, has_alert: bool):
    """绘制预警图表"""
    if df.empty:
        return None
    
    stock_name = stock_config['name']
    alert_type = stock_config['alert_type']
    
    # 确保在主线程中使用matplotlib
    if threading.current_thread().name != 'MainThread':
        print(f"  ⚠️  图表绘制需要在主线程中执行，跳过绘制")
        return None
    
    if alert_type == 'golden_cross':
        # 金叉预警图表
        ma_short = stock_config['ma_short']
        ma_long = stock_config['ma_long']
        
        # 过滤掉均线数据不足的行
        plot_df = df.dropna(subset=[f'ma{ma_short}', f'ma{ma_long}']).copy()
        
        if plot_df.empty:
            return None
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
        
        # 图1：股价和均线
        ax1.plot(plot_df["date"], plot_df["close"], 
                 color="#2ca02c", linewidth=1.5, label="收盘价")
        ax1.plot(plot_df["date"], plot_df[f'ma{ma_short}'], 
                 color="#ff7f0e", linewidth=1.5, label=f"{ma_short}日均线")
        ax1.plot(plot_df["date"], plot_df[f'ma{ma_long}'], 
                 color="#d62728", linewidth=1.5, label=f"{ma_long}日均线")
        
        # 标记金叉点
        golden_crosses = plot_df[plot_df['golden_cross']]
        if not golden_crosses.empty:
            # 只添加一次图例
            ax1.scatter(golden_crosses.iloc[0]['date'], golden_crosses.iloc[0][f'ma{ma_short}'], 
                       color='gold', s=200, marker='^', zorder=5, label='金叉')
            ax1.annotate('金叉', xy=(golden_crosses.iloc[0]['date'], golden_crosses.iloc[0][f'ma{ma_short}']), 
                        xytext=(10, 10), textcoords='offset points',
                        fontsize=10, color='gold', fontweight='bold')
            # 绘制其他点但不添加图例
            if len(golden_crosses) > 1:
                for _, row in golden_crosses.iloc[1:].iterrows():
                    ax1.scatter(row['date'], row[f'ma{ma_short}'], 
                               color='gold', s=200, marker='^', zorder=5)
                    ax1.annotate('金叉', xy=(row['date'], row[f'ma{ma_short}']), 
                                xytext=(10, 10), textcoords='offset points',
                                fontsize=10, color='gold', fontweight='bold')
        
        ax1.set_ylabel("价格", fontsize=12)
        ax1.set_title(f"{stock_name} - {ma_short}日均线 vs {ma_long}日均线", 
                      fontsize=14, fontweight="bold")
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc="upper left", fontsize=10)
        
        # 图2：均线差值
        ax2.plot(plot_df["date"], plot_df['ma_diff'], 
                 color="#9467bd", linewidth=1.5, label="均线差值")
        ax2.axhline(y=0, color="#2ca02c", linestyle="--", linewidth=1, alpha=0.7)
        
        # 标记金叉点
        for _, row in golden_crosses.iterrows():
            ax2.scatter(row['date'], row['ma_diff'], 
                       color='gold', s=200, marker='^', zorder=5)
            ax2.annotate('金叉', xy=(row['date'], row['ma_diff']), 
                        xytext=(10, 10), textcoords='offset points',
                        fontsize=10, color='gold', fontweight='bold')
        
        ax2.set_ylabel("均线差值", fontsize=12)
        ax2.set_xlabel("日期", fontsize=12)
        ax2.set_title(f"{stock_name} - 均线差值（正数表示{ma_short}日均线在{ma_long}日均线之上）", 
                      fontsize=12, fontweight="bold")
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc="upper left", fontsize=10)
        
    elif alert_type == 'three_above_ma':
        # 连续三根k线站上20日均线预警图表
        ma_line = stock_config['ma_line']
        
        # 过滤掉均线数据不足的行
        plot_df = df.dropna(subset=[f'ma{ma_line}']).copy()
        
        if plot_df.empty:
            return None
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
        
        # 图1：股价和均线
        ax1.plot(plot_df["date"], plot_df["close"], 
                 color="#2ca02c", linewidth=1.5, label="收盘价")
        ax1.plot(plot_df["date"], plot_df[f'ma{ma_line}'], 
                 color="#d62728", linewidth=2, label=f"{ma_line}日均线")
        
        # 标记站上均线的点
        above_ma_points = plot_df[plot_df['above_ma']]
        if not above_ma_points.empty:
            # 只添加一次图例
            ax1.scatter(above_ma_points.iloc[0]['date'], above_ma_points.iloc[0]['close'], 
                       color='green', s=50, marker='o', zorder=5, label='站在均线上方')
            # 绘制其他点但不添加图例
            if len(above_ma_points) > 1:
                for _, row in above_ma_points.iloc[1:].iterrows():
                    ax1.scatter(row['date'], row['close'], 
                               color='green', s=50, marker='o', zorder=5)
        
        # 标记第一次出现连续三根站上均线的点
        if 'first_three_above_ma' in plot_df.columns:
            three_above_ma_points = plot_df[plot_df['first_three_above_ma']]
        else:
            three_above_ma_points = plot_df[plot_df['three_above_ma']]
        
        if not three_above_ma_points.empty:
            # 只添加一次图例
            ax1.scatter(three_above_ma_points.iloc[0]['date'], three_above_ma_points.iloc[0]['close'], 
                       color='gold', s=200, marker='^', zorder=6, label='连续三根站上均线')
            ax1.annotate('连续三根', xy=(three_above_ma_points.iloc[0]['date'], three_above_ma_points.iloc[0]['close']), 
                        xytext=(10, 10), textcoords='offset points',
                        fontsize=10, color='gold', fontweight='bold')
            # 绘制其他点但不添加图例
            if len(three_above_ma_points) > 1:
                for _, row in three_above_ma_points.iloc[1:].iterrows():
                    ax1.scatter(row['date'], row['close'], 
                               color='gold', s=200, marker='^', zorder=6)
                    ax1.annotate('连续三根', xy=(row['date'], row['close']), 
                                xytext=(10, 10), textcoords='offset points',
                                fontsize=10, color='gold', fontweight='bold')
        
        ax1.set_ylabel("价格", fontsize=12)
        ax1.set_title(f"{stock_name} - 收盘价 vs {ma_line}日均线", 
                      fontsize=14, fontweight="bold")
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc="upper left", fontsize=10)
        
        # 图2：连续站上均线天数
        ax2.plot(plot_df["date"], plot_df['consecutive_above_ma'], 
                 color="#9467bd", linewidth=1.5, label="连续站上均线天数")
        ax2.axhline(y=3, color="#d62728", linestyle="--", linewidth=1, alpha=0.7, label="预警阈值（3天）")
        
        # 标记第一次出现连续三根站上均线的点
        for _, row in three_above_ma_points.iterrows():
            ax2.scatter(row['date'], row['consecutive_above_ma'], 
                       color='gold', s=200, marker='^', zorder=5)
            ax2.annotate('预警', xy=(row['date'], row['consecutive_above_ma']), 
                        xytext=(10, 10), textcoords='offset points',
                        fontsize=10, color='gold', fontweight='bold')
        
        ax2.set_ylabel("连续站上均线天数", fontsize=12)
        ax2.set_xlabel("日期", fontsize=12)
        ax2.set_title(f"{stock_name} - 连续站上{ma_line}日均线天数", 
                      fontsize=12, fontweight="bold")
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc="upper left", fontsize=10)
    
    elif alert_type == 'three_carriers_above_ma':
        # 三个运营商都站在20日均线上方预警图表
        ma_line = stock_config['ma_line']
        carriers = stock_config['carriers']
        
        # 创建一个简单的表格图表
        fig, ax = plt.subplots(figsize=(12, 8))
        ax.axis('tight')
        ax.axis('off')
        
        # 构建表格数据
        table_data = []
        for carrier in carriers:
            carrier_name = carrier['name']
            carrier_code = carrier['code']
            
            # 获取运营商股票数据
            carrier_df = get_stock_data(carrier_code, carrier_name)
            
            if carrier_df.empty:
                table_data.append([carrier_name, carrier_code, 'N/A', 'N/A', 'N/A'])
            else:
                # 计算20日均线
                carrier_df[f'ma{ma_line}'] = carrier_df['close'].rolling(window=ma_line).mean()
                
                # 获取最新数据
                latest_carrier_row = carrier_df.iloc[-1]
                latest_close = latest_carrier_row['close']
                latest_ma = latest_carrier_row[f'ma{ma_line}']
                above_ma = latest_close > latest_ma
                status = '✓ 站在上方' if above_ma else '✗ 站在下方'
                status_color = 'green' if above_ma else 'red'
                
                table_data.append([carrier_name, carrier_code, f'{latest_close:.2f}', f'{latest_ma:.2f}', status])
        
        # 创建表格
        table = ax.table(cellText=table_data, 
                       colLabels=['运营商名称', '股票代码', '最新收盘价', f'{ma_line}日均线', '状态'],
                       colWidths=[0.2, 0.15, 0.15, 0.15, 0.35],
                       cellLoc='center',
                       loc='center')
        
        # 设置表格样式
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.5)
        
        # 设置标题
        ax.set_title(f"三大运营商 - 20日均线状态检查", 
                     fontsize=14, fontweight="bold", pad=20)
        
        # 添加说明文字
        plt.figtext(0.5, 0.1, f"检查时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n预警条件：三个运营商都站在20日均线上方",
                    ha="center", fontsize=10, color="gray")
    
    # 格式化日期
    if alert_type != 'three_carriers_above_ma':
        for ax in [ax1, ax2]:
            fig.autofmt_xdate()
    
    try:
        plt.tight_layout()
    except Exception as e:
        print(f"  ⚠️  图表布局警告：{e}")
    
    # 保存图片
    latest_date = df.iloc[-1]["date"].strftime("%Y%m%d")
    alert_status = "预警" if has_alert else "正常"
    save_path = os.path.join(PICTURE_DIR, f"{stock_name}_均线预警_{latest_date}_{alert_status}.png")
    
    try:
        plt.savefig(save_path, bbox_inches='tight', pad_inches=0.1)
        plt.close()
        
        print(f"  ✅ {stock_name}预警图表已保存：{save_path}")
        return save_path
    except Exception as e:
        print(f"  ❌ 图表保存失败：{e}")
        plt.close()
        return None

# ===================== 邮件发送函数 =====================
def send_alert_email(alert_info: dict, chart_path: str, stock_config: dict):
    """发送预警邮件"""
    if not alert_info['has_alert']:
        print("ℹ️  无预警信号，不发送邮件")
        return
    
    stock_name = stock_config['name']
    stock_code = stock_config['code']
    alert_type = stock_config['alert_type']
    latest_data = alert_info['latest_data']
    
    # 构建邮件主体
    msg = MIMEMultipart('related')
    msg['From'] = EMAIL_CONFIG['sender']
    msg['To'] = EMAIL_CONFIG['receiver']
    msg['Subject'] = Header(f"股票预警_{stock_name}_{datetime.now().strftime('%Y%m%d')}", 'utf-8')
    
    if alert_type == 'golden_cross':
        # 金叉预警邮件内容
        ma_short = stock_config['ma_short']
        ma_long = stock_config['ma_long']
        
        # 构建HTML内容
        html_content = f"""
        <html>
          <body>
            <h2>🚨 股票预警提醒（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）</h2>
            
            <h3>📊 预警信息：</h3>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
              <tr style="background-color: #f0f0f0;">
                <th>股票名称</th>
                <th>股票代码</th>
                <th>预警类型</th>
                <th>预警时间</th>
              </tr>
              <tr>
                <td><b>{stock_name}</b></td>
                <td>{stock_code}</td>
                <td><b style="color: gold;">{alert_info['alert_type']}</b></td>
                <td>{latest_data['date']}</td>
              </tr>
            </table>
            <br>
            
            <h3>📈 最新数据：</h3>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
              <tr style="background-color: #f0f0f0;">
                <th>收盘价</th>
                <th>{ma_short}日均线</th>
                <th>{ma_long}日均线</th>
                <th>均线差值</th>
              </tr>
              <tr>
                <td><b>{latest_data['close']:.2f}</b></td>
                <td>{latest_data[f'ma{ma_short}']:.2f}</td>
                <td>{latest_data[f'ma{ma_long}']:.2f}</td>
                <td><b style="color: {'green' if latest_data['ma_diff'] > 0 else 'red'};">{latest_data['ma_diff']:.2f}</b></td>
              </tr>
            </table>
            <br>
            
            <h3>💡 预警说明：</h3>
            <p><b>{ma_short}日均线</b>刚刚上穿<b>{ma_long}日均线</b>，形成<b>金叉</b>信号。</p>
            <p>这通常被视为<b>买入信号</b>，表明短期趋势转强。</p>
            <br>
            
            <h3>📊 预警图表：</h3>
            <img src="cid:alert_chart" style="border: none; max-width: 100%; display: block;" /><br>
            
            <br>
            <p>⚠️ 本预警仅供参考，不构成投资建议</p>
            <p>⏰ 预警时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
          </body>
        </html>
        """
    
    elif alert_type == 'three_above_ma':
        # 连续三根k线站上20日均线预警邮件内容
        ma_line = stock_config['ma_line']
        
        # 构建HTML内容
        html_content = f"""
        <html>
          <body>
            <h2>🚨 股票预警提醒（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）</h2>
            
            <h3>📊 预警信息：</h3>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
              <tr style="background-color: #f0f0f0;">
                <th>股票名称</th>
                <th>股票代码</th>
                <th>预警类型</th>
                <th>预警时间</th>
              </tr>
              <tr>
                <td><b>{stock_name}</b></td>
                <td>{stock_code}</td>
                <td><b style="color: gold;">{alert_info['alert_type']}</b></td>
                <td>{latest_data['date']}</td>
              </tr>
            </table>
            <br>
            
            <h3>📈 最新数据：</h3>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
              <tr style="background-color: #f0f0f0;">
                <th>收盘价</th>
                <th>{ma_line}日均线</th>
                <th>连续站上均线天数</th>
                <th>状态</th>
              </tr>
              <tr>
                <td><b>{latest_data['close']:.2f}</b></td>
                <td>{latest_data[f'ma{ma_line}']:.2f}</td>
                <td><b>{latest_data['consecutive_above_ma']}</b></td>
                <td><b style="color: green;">站在均线上方</b></td>
              </tr>
            </table>
            <br>
            
            <h3>💡 预警说明：</h3>
            <p><b>{stock_name}</b>连续<b>3</b>个交易日收盘价站在<b>{ma_line}日均线</b>上方。</p>
            <p>这通常被视为<b>强势信号</b>，表明股价可能继续上涨。</p>
            <br>
            
            <h3>📊 预警图表：</h3>
            <img src="cid:alert_chart" style="border: none; max-width: 100%; display: block;" /><br>
            
            <br>
            <p>⚠️ 本预警仅供参考，不构成投资建议</p>
            <p>⏰ 预警时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
          </body>
        </html>
        """
    
    elif alert_type == 'three_carriers_above_ma':
        # 三个运营商都站在20日均线上方预警邮件内容
        ma_line = stock_config['ma_line']
        carriers_data = latest_data['carriers']
        
        # 构建HTML内容
        html_content = f"""
        <html>
          <body>
            <h2>🚨 股票预警提醒（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）</h2>
            
            <h3>📊 预警信息：</h3>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
              <tr style="background-color: #f0f0f0;">
                <th>组合名称</th>
                <th>预警类型</th>
                <th>预警时间</th>
                <th>操作建议</th>
              </tr>
              <tr>
                <td><b>{stock_name}</b></td>
                <td><b style="color: gold;">{alert_info['alert_type']}</b></td>
                <td>{latest_data['date']}</td>
                <td><b style="color: green;">建议买入</b></td>
              </tr>
            </table>
            <br>
            
            <h3>📈 运营商数据详情：</h3>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
              <tr style="background-color: #f0f0f0;">
                <th>运营商名称</th>
                <th>股票代码</th>
                <th>最新收盘价</th>
                <th>{ma_line}日均线</th>
                <th>状态</th>
              </tr>
            """
        
        # 添加运营商数据行
        for carrier in carriers_data:
            carrier_name = carrier['name']
            carrier_code = carrier['code']
            close = carrier['close']
            ma_value = carrier[f'ma{ma_line}']
            above_ma = carrier['above_ma']
            status = '✓ 站在上方' if above_ma else '✗ 站在下方'
            status_color = 'green' if above_ma else 'red'
            
            html_content += f"<tr><td><b>{carrier_name}</b></td><td>{carrier_code}</td><td>{close:.2f}</td><td>{ma_value:.2f}</td><td><b style=\"color: {status_color};\">{status}</b></td></tr>"
        
        # 完成HTML内容
        html_content += f"""
            </table>
            <br>
            
            <h3>💡 预警说明：</h3>
            <p>三大运营商（中国移动、中国联通、中国电信）<b>全部</b>站在<b>{ma_line}日均线</b>上方。</p>
            <p>这通常被视为<b>行业强势信号</b>，表明通信运营板块整体向好。</p>
            <p><b>操作建议：</b>可以考虑买入相关股票，分散投资于三大运营商。</p>
            <br>
            
            <h3>📊 预警图表：</h3>
            <img src="cid:alert_chart" style="border: none; max-width: 100%; display: block;" /><br>
            
            <br>
            <p>⚠️ 本预警仅供参考，不构成投资建议</p>
            <p>⏰ 预警时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
          </body>
        </html>
        """
    
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))
    
    # 嵌入图片
    if chart_path:
        try:
            with open(chart_path, 'rb') as f:
                img_data = f.read()
                img = MIMEImage(img_data, _subtype='png')
                img.add_header('Content-ID', '<alert_chart>')
                msg.attach(img)
        except Exception as e:
            print(f"⚠️ 图表嵌入失败：{e}")
    
    # 发送邮件
    try:
        server = smtplib.SMTP_SSL(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'], timeout=30)
        server.login(EMAIL_CONFIG['sender'], EMAIL_CONFIG['auth_code'])
        server.sendmail(
            from_addr=EMAIL_CONFIG['sender'],
            to_addrs=EMAIL_CONFIG['receiver'].split(','),
            msg=msg.as_string()
        )
        server.quit()
        print(f"\n✅ 预警邮件发送成功！已发送至：{EMAIL_CONFIG['receiver']}")
    except smtplib.SMTPAuthenticationError:
        print("❌ 邮件发送失败：授权码错误/邮箱未开启SMTP服务")
    except smtplib.SMTPRecipientsRefused:
        print("❌ 邮件发送失败：收件人邮箱地址错误")
    except Exception as e:
        print(f"❌ 邮件发送失败：{str(e)}")

# ===================== 判断是否为交易日 =====================
def is_trading_day():
    """判断今天是否是交易日"""
    try:
        today = datetime.now().strftime('%Y%m%d')
        trade_date_df = ak.tool_trade_date_hist_sina()
        today_str = datetime.now().strftime('%Y-%m-%d')
        trade_dates = pd.to_datetime(trade_date_df['trade_date']).dt.strftime('%Y-%m-%d').values
        is_trade_day = today_str in trade_dates
        
        if is_trade_day:
            print(f"✅ {today_str} 是交易日，继续执行预警检查")
        else:
            print(f"⏸️ {today_str} 是非交易日，跳过预警检查")
            
        return is_trade_day
    except Exception as e:
        print(f"⚠️ 交易日历获取失败: {e}，使用备用判断方法")
        
        # 备用方法: 基于星期判断
        weekday = datetime.now().weekday()
        is_trade_day = weekday < 5
        
        if is_trade_day:
            print(f"✅ 基于星期判断：今天是工作日，假设为交易日")
        else:
            print(f"⏸️ 基于星期判断：今天是周末，假设为非交易日")
            
        return is_trade_day

# ===================== 输出预警配置到txt文件 =====================
def output_alert_configs():
    """输出当前正在执行的预警配置到txt文件"""
    output_dir = os.path.join(os.getcwd(), 'config')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    output_file = os.path.join(output_dir, '预警配置列表.txt')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"股票预警系统配置列表\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*80 + "\n")
        
        for i, stock_config in enumerate(STOCK_CONFIGS, 1):
            f.write(f"[{i}] 股票名称: {stock_config['name']}\n")
            f.write(f"   股票代码: {stock_config['code']}\n")
            f.write(f"   预警类型: {stock_config['alert_type']}\n")
            
            if stock_config['alert_type'] == 'golden_cross':
                f.write(f"   短期均线: {stock_config['ma_short']}日\n")
                f.write(f"   长期均线: {stock_config['ma_long']}日\n")
                f.write(f"   预警条件: {stock_config['ma_short']}日均线上穿{stock_config['ma_long']}日均线\n")
            elif stock_config['alert_type'] == 'three_above_ma':
                f.write(f"   均线参数: {stock_config['ma_line']}日\n")
                f.write(f"   预警条件: 连续3个交易日收盘价站在{stock_config['ma_line']}日均线上方\n")
            elif stock_config['alert_type'] == 'three_carriers_above_ma':
                f.write(f"   均线参数: {stock_config['ma_line']}日\n")
                f.write(f"   预警条件: 三大运营商都站在{stock_config['ma_line']}日均线上方\n")
                f.write(f"   包含股票: {', '.join([carrier['name'] for carrier in stock_config['carriers']])}\n")
            
            f.write("-"*80 + "\n")
        
        f.write("\n执行时间安排:\n")
        f.write("- 每个工作日 10:00\n")
        f.write("- 每个工作日 14:00\n")
        f.write("- 每个工作日 16:30\n")
        f.write("- 非交易日自动跳过\n")
        
        f.write("\n管理说明:\n")
        f.write("- 新增预警: 在STOCK_CONFIGS列表中添加新的配置字典\n")
        f.write("- 删除预警: 从STOCK_CONFIGS列表中移除对应的配置字典\n")
        f.write("- 修改预警: 编辑STOCK_CONFIGS列表中对应的配置字典\n")
    
    print(f"✅ 预警配置列表已输出到: {output_file}")
    return output_file

# ===================== 生成HTML输出函数 =====================
def generate_html_output(results):
    """生成HTML输出，将预警结果保存到alert_output文件夹中的以日期命名的子文件夹中"""
    # 创建以日期命名的子文件夹
    today_date = datetime.now().strftime('%Y%m%d')
    html_output_dir = os.path.join(ALERT_OUTPUT_DIR, today_date)
    if not os.path.exists(html_output_dir):
        os.makedirs(html_output_dir)
    
    # 创建HTML文件
    html_file = os.path.join(html_output_dir, f'预警结果_{today_date}.html')
    
    # 构建HTML内容
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>股票预警结果 - {today_date}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background-color: #f5f5f5;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background-color: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
            }}
            h1 {{
                color: #333;
                text-align: center;
                margin-bottom: 30px;
            }}
            h2 {{
                color: #555;
                margin-top: 30px;
                margin-bottom: 20px;
                border-bottom: 2px solid #f0f0f0;
                padding-bottom: 10px;
            }}
            .summary {{
                background-color: #f9f9f9;
                padding: 20px;
                border-radius: 5px;
                margin-bottom: 30px;
            }}
            .summary p {{
                margin: 10px 0;
                font-size: 16px;
            }}
            .summary strong {{
                color: #333;
            }}
            .stock-table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 30px;
            }}
            .stock-table th,
            .stock-table td {{
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #f0f0f0;
            }}
            .stock-table th {{
                background-color: #f5f5f5;
                font-weight: bold;
                color: #333;
            }}
            .stock-table tr:hover {{
                background-color: #f9f9f9;
            }}
            .alert-row {{
                background-color: #fff3cd;
                font-weight: bold;
            }}
            .alert-row td:first-child {{
                color: #856404;
            }}
            .footer {{
                text-align: center;
                margin-top: 50px;
                padding-top: 20px;
                border-top: 2px solid #f0f0f0;
                color: #666;
                font-size: 14px;
            }}
            .timestamp {{
                text-align: right;
                color: #999;
                font-size: 14px;
                margin-bottom: 20px;
            }}
            .chart-container {{
                margin: 30px 0;
                padding: 20px;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                background-color: #f9f9f9;
            }}
            .chart-container h3 {{
                margin-top: 0;
                color: #555;
                margin-bottom: 15px;
            }}
            .chart-image {{
                max-width: 100%;
                height: auto;
                border-radius: 3px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                display: block;
                margin: 0 auto;
            }}
            .no-chart {{
                text-align: center;
                color: #999;
                padding: 20px;
                font-style: italic;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>股票预警结果</h1>
            <div class="timestamp">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            
            <div class="summary">
                <h2>执行结果汇总</h2>
                <p><strong>总计股票数:</strong> {len(STOCK_CONFIGS)}只</p>
                <p><strong>处理股票数:</strong> {len(results)}只</p>
                <p><strong>预警股票数:</strong> {sum(1 for result in results if result['has_alert'])}只</p>
                <p><strong>执行时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <h2>预警详情</h2>
            <table class="stock-table">
                <tr>
                    <th>股票名称</th>
                    <th>股票代码</th>
                    <th>预警类型</th>
                    <th>预警状态</th>
                </tr>
            """
    
    # 添加股票预警结果行
    for result in results:
        stock_name = result['stock_name']
        stock_code = result['stock_code']
        alert_type = result['alert_type']
        has_alert = result['has_alert']
        
        alert_status = '🚨 预警触发' if has_alert else '✅ 无预警信号'
        row_class = 'alert-row' if has_alert else ''
        
        html_content += f"""
                <tr class="{row_class}">
                    <td>{stock_name}</td>
                    <td>{stock_code}</td>
                    <td>{alert_type}</td>
                    <td>{alert_status}</td>
                </tr>
            """
    
    # 完成HTML内容
    html_content += f"""
            </table>
            
            <h2>股票图表</h2>
            <div class="chart-container">
            """
    
    # 查找并添加图片
    for stock_config in STOCK_CONFIGS:
        stock_name = stock_config['name']
        # 查找当天的图片文件
        latest_date = datetime.now().strftime('%Y%m%d')
        # 构建可能的图片文件名
        possible_filenames = [
            f"{stock_name}_均线预警_{latest_date}_预警.png",
            f"{stock_name}_均线预警_{latest_date}_正常.png"
        ]
        
        # 检查图片是否存在
        chart_path = None
        for filename in possible_filenames:
            full_path = os.path.join(PICTURE_DIR, filename)
            if os.path.exists(full_path):
                chart_path = full_path
                break
        
        # 添加图表到HTML
        if chart_path:
            # 生成相对路径
            relative_path = os.path.relpath(chart_path, html_output_dir)
            html_content += f"""
                <h3>{stock_name}</h3>
                <img src="{relative_path}" alt="{stock_name}图表" class="chart-image">
            """
        else:
            html_content += f"""
                <h3>{stock_name}</h3>
                <div class="no-chart">暂无图表数据</div>
            """
    
    # 完成HTML内容
    html_content += f"""
            </div>
            
            <div class="footer">
                <p>© {datetime.now().year} 股票预警系统 | 本预警仅供参考，不构成投资建议</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # 写入HTML文件
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ HTML输出已生成: {html_file}")
    return html_file

# ===================== 单个股票预警检查函数 =====================
def check_stock_alert(stock_config):
    """检查单个股票的预警信号"""
    stock_name = stock_config['name']
    stock_code = stock_config['code']
    alert_type = stock_config['alert_type']
    
    print(f"\n🔍 开始检查：{stock_name}({stock_code}) - {alert_type}")
    print("-"*80)
    
    try:
        # 1. 获取股票数据
        df = get_stock_data(stock_code, stock_name)
        
        if df.empty:
            print(f"❌ 未获取到{stock_name}数据，跳过该股票")
            return None
        
        # 2. 计算均线并检查预警
        alert_info = calculate_ma_and_check_alert(df, stock_config)
        
        # 3. 输出预警结果
        print("\n" + "="*80)
        print(f"股票预警检查结果（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        latest_data = alert_info['latest_data']
        print(f"📊 {stock_name}({stock_code})")
        
        if alert_type == 'golden_cross':
            # 金叉预警类型输出
            print(f"   收盘价: {latest_data['close']:.2f}")
            ma_short = stock_config['ma_short']
            ma_long = stock_config['ma_long']
            print(f"   {ma_short}日均线: {latest_data[f'ma{ma_short}']:.2f}")
            print(f"   {ma_long}日均线: {latest_data[f'ma{ma_long}']:.2f}")
            print(f"   均线差值: {latest_data['ma_diff']:.2f}")
            
            if alert_info['has_alert']:
                print(f"\n🚨 预警触发！{alert_info['alert_type']}")
                print(f"   {ma_short}日均线刚刚上穿{ma_long}日均线")
            else:
                print(f"\n✅ 无预警信号")
        
        elif alert_type == 'three_above_ma':
            # 连续站上均线预警类型输出
            print(f"   收盘价: {latest_data['close']:.2f}")
            ma_line = stock_config['ma_line']
            print(f"   {ma_line}日均线: {latest_data[f'ma{ma_line}']:.2f}")
            print(f"   连续站上均线天数: {latest_data['consecutive_above_ma']}")
            
            if alert_info['has_alert']:
                print(f"\n🚨 预警触发！{alert_info['alert_type']}")
                print(f"   连续3个交易日收盘价站在{ma_line}日均线上方")
            else:
                print(f"\n✅ 无预警信号")
        
        print("="*80)
        
        # 4. 返回结果（包含数据以便后续在主线程中绘制图表）
        return {
            'stock_name': stock_name,
            'stock_code': stock_code,
            'has_alert': alert_info['has_alert'],
            'alert_type': alert_info['alert_type'],
            'df': alert_info['df'],
            'stock_config': stock_config
        }
        
    except Exception as e:
        print(f"\n❌ {stock_name}检查失败：{str(e)}")
        import traceback
        traceback.print_exc()
        return None

# ===================== 主函数 =====================
if __name__ == "__main__":
    print("="*100)
    print(f"股票预警系统启动（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*100)
    
    # 检查是否为交易日
    if not is_trading_day():
        print("\n⏸️  非交易日，系统自动退出")
        exit()
    
    # 输出预警配置
    output_alert_configs()
    
    # 使用多线程检查股票预警
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(STOCK_CONFIGS)) as executor:
        # 提交任务
        future_to_stock = {executor.submit(check_stock_alert, stock_config): stock_config for stock_config in STOCK_CONFIGS}
        
        # 收集结果
        for future in concurrent.futures.as_completed(future_to_stock):
            stock_config = future_to_stock[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                print(f"❌ 线程执行失败：{e}")
    
    # 在主线程中绘制图表并发送邮件
    print("\n" + "="*80)
    print("在主线程中绘制图表并发送邮件")
    print("="*80)
    
    chart_paths = {}
    for result in results:
        stock_name = result['stock_name']
        stock_config = result['stock_config']
        has_alert = result['has_alert']
        df = result['df']
        
        # 绘制图表
        print(f"\n📊 正在绘制{stock_name}图表...")
        chart_path = plot_alert_chart(df, stock_config, has_alert)
        chart_paths[stock_name] = chart_path
        
        # 发送邮件
        if has_alert:
            print(f"\n📧 正在发送{stock_name}预警邮件...")
            # 重新计算预警信息（确保数据完整）
            alert_df = get_stock_data(stock_config['code'], stock_config['name'])
            if not alert_df.empty:
                alert_info = calculate_ma_and_check_alert(alert_df, stock_config)
                send_alert_email(alert_info, chart_path, stock_config)
    
    # 生成HTML输出
    try:
        html_file = generate_html_output(results)
        print(f"\n✅ HTML预警结果已生成：{html_file}")
    except Exception as e:
        print(f"\n❌ 生成HTML输出失败：{e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*100)
    print(f"股票预警系统执行完成（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*100)