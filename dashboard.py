import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import numpy as np
from supabase import create_client, Client
from fpdf import FPDF
import io

# --- 1. 页面配置 ---
st.set_page_config(
    page_title="SKG Dashboard",
    page_icon="📊",
    layout="wide"
)

# --- 2. 初始化 Supabase 连接 ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

# --- PDF 报告样式定义 ---
class SKG_Report(FPDF):
    def __init__(self, date_str):
        super().__init__()
        self.date_str = date_str
        # 商务色调：深海军蓝 & 柔和灰
        self.primary_color = (26, 54, 104)   # Navy Blue
        self.secondary_color = (240, 244, 248) # Light Blue Gray (背景色)
        self.text_color = (40, 40, 40)       # 深灰文字

    def add_cover_page(self):
        self.add_page()
        # 背景装饰
        self.set_fill_color(*self.primary_color)
        self.rect(0, 0, 210, 100, 'F') 
        
        # 标题
        self.set_y(40)
        self.set_text_color(255, 255, 255)
        self.set_font('helvetica', 'B', 28)
        self.cell(0, 20, 'BUSINESS ANALYSIS REPORT', 0, 1, 'C')
        self.set_font('helvetica', '', 14)
        self.cell(0, 10, f'Reporting Period: {self.date_str}', 0, 1, 'C')
        
        # 底部品牌标识
        self.set_y(250)
        self.set_text_color(*self.primary_color)
        self.set_font('helvetica', 'B', 16)
        self.cell(0, 10, 'SKG GLOBAL INVENTORY & SALES', 0, 1, 'C')
        self.set_draw_color(*self.primary_color)
        self.line(80, 262, 130, 262)

    def header(self):
        self.set_fill_color(*self.primary_color)
        self.rect(0, 0, 210, 15, 'F')
        self.set_y(4)
        self.set_text_color(255, 255, 255)
        self.set_font('helvetica', 'B', 10)
        self.cell(0, 10, 'SKG CONFIDENTIAL - BUSINESS INTELLIGENCE', 0, 0, 'L')
        self.set_font('helvetica', 'I', 9)
        self.cell(0, 10, f'Period: {self.date_str} ', 0, 0, 'R')
        self.ln(15)

    def footer(self):
        if self.page_no() > 1:
            self.set_y(-15)
            self.set_font('helvetica', 'I', 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, f'Page {self.page_no()} | Generated on {datetime.now().strftime("%Y-%m-%d")}', 0, 0, 'C')

supabase = init_connection()

# --- 3. 简易登录 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    # 登录界面容器
    with st.container():
        st.subheader("Login / 登入")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        # 添加登录按钮
        if st.button("Login", type="primary"):
            # 验证逻辑
            if (username == st.secrets["DB_USERNAME"] and 
                password == st.secrets["DB_PASSWORD"]):
                st.session_state["password_correct"] = True
                st.rerun() # 验证成功后刷新页面以进入主程序
            else:
                st.error("😕 User not found or password incorrect")
                st.session_state["password_correct"] = False
                
    return False

if not check_password():
    st.stop()

# --- 4. 数据加载 (从 Supabase 读取) ---
@st.cache_data(ttl=600) # 每10分钟清理一次缓存，或手动刷新
def load_data_from_supabase():
    try:
        # 1. 加载主表 (必须包含 Name, Code, Type 三个字段)
        wh_res = supabase.table("warehouse").select("warehouse_code, warehouse_name, warehouse_type").execute()
        df_wh_master = pd.DataFrame(wh_res.data)
        if not df_wh_master.empty:
            # 清洗：去空格 + 转大写 (Code 建议转大写，Name 建议只去空格)
            df_wh_master['warehouse_code'] = df_wh_master['warehouse_code'].astype(str).str.strip().str.upper()
            df_wh_master['warehouse_name'] = df_wh_master['warehouse_name'].astype(str).str.strip()
            df_wh_master['warehouse_type'] = df_wh_master['warehouse_type'].astype(str).str.strip()

        ar_res = supabase.table("ar").select("ar_code, ar_name, ar_type").execute()
        df_ar_master = pd.DataFrame(ar_res.data)
        if not df_ar_master.empty:
            df_ar_master['ar_code'] = df_ar_master['ar_code'].astype(str).str.strip().str.upper()
            df_ar_master['ar_name'] = df_ar_master['ar_name'].astype(str).str.strip()
            df_ar_master['ar_type'] = df_ar_master['ar_type'].astype(str).str.strip()

        # 2. 读取库存表并清洗
        stock_response = supabase.table("stock_details").select("*").execute()
        df_stock = pd.DataFrame(stock_response.data)
        if not df_stock.empty:
            df_stock['Warehouse Code'] = df_stock['Warehouse Code'].astype(str).str.strip().str.upper()
            df_stock['Warehouse Name'] = df_stock['Warehouse Name'].astype(str).str.strip()
            
            # --- 关联主表 (使用组合键: Name + Code) ---
            if not df_wh_master.empty:
                wh_m = df_wh_master.rename(columns={'warehouse_type': 'Master_WH_Type'})
                df_stock = pd.merge(
                    df_stock, wh_m, 
                    left_on=['Warehouse Code', 'Warehouse Name'], 
                    right_on=['warehouse_code', 'warehouse_name'], 
                    how='left'
                )
                # 优先使用主表类型
                df_stock['warehouse_type'] = df_stock['Master_WH_Type'].fillna(df_stock['warehouse_type'])

        # 3. 读取销售表并清洗
        sales_response = supabase.table("sales_details").select("*").execute()
        df_sales = pd.DataFrame(sales_response.data)
        if not df_sales.empty:
            df_sales['Warehouse Code'] = df_sales['Warehouse Code'].astype(str).str.strip().str.upper()
            df_sales['Warehouse Name'] = df_sales['Warehouse Name'].astype(str).str.strip()
            df_sales['AR Code'] = df_sales['AR Code'].astype(str).str.strip().str.upper()
            df_sales['AR Name'] = df_sales['AR Name'].astype(str).str.strip()

            # --- 关联仓库 (Name + Code) ---
            if not df_wh_master.empty:
                wh_m = df_wh_master.rename(columns={'warehouse_type': 'Master_WH_Type'})
                df_sales = pd.merge(
                    df_sales, wh_m, 
                    left_on=['Warehouse Code', 'Warehouse Name'], 
                    right_on=['warehouse_code', 'warehouse_name'], 
                    how='left'
                )
                df_sales['warehouse_type'] = df_sales['Master_WH_Type'].fillna(df_sales['warehouse_type'])

            # --- 关联 AR (Name + Code) ---
            if not df_ar_master.empty:
                ar_m = df_ar_master.rename(columns={'ar_type': 'Master_AR_Type'})
                df_sales = pd.merge(
                    df_sales, ar_m, 
                    left_on=['AR Code', 'AR Name'], 
                    right_on=['ar_code', 'ar_name'], 
                    how='left'
                )
                df_sales['ar_type'] = df_sales['Master_AR_Type'].fillna(df_sales['ar_type'])

        # 4. 统一重命名
        final_rename = {
            'warehouse_type': 'Warehouse Type',
            'ar_type': 'AR Type',
            'Warehouse Name': 'Warehouse Name',
            'Warehouse Code': 'Warehouse Code',
            'Invoice Number': 'Invoice Number'
        }
        df_stock = df_stock.rename(columns=final_rename)
        df_sales = df_sales.rename(columns=final_rename)
        
        return df_stock, df_sales
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame(), pd.DataFrame()

df_stock_raw, df_sales_raw = load_data_from_supabase()

if df_stock_raw.empty or df_sales_raw.empty:
    st.warning("Database is empty or connection failed.")
    st.stop()

# --- 5. 数据预处理  ---

# 4.1 处理 Sales Data
df_sales = df_sales_raw.copy()
# 因为 Supabase 中 Date 是 text 类型，确保转换为 datetime
df_sales['Date'] = pd.to_datetime(df_sales['Date'])

# 自动提取产品类别 (保留这个功能，因为Excel通常没有Category列)
def extract_category(stock_name):
    name = str(stock_name).lower()
    if 'eye' in name: return 'Eye Massager'
    if 'neck' in name or 'cervical' in name: return 'Neck/Cervical'
    if 'waist' in name: return 'Waist Massager'
    if 'knee' in name: return 'Knee Massager'
    if 'gun' in name or 'fascia' in name: return 'Massage Gun'
    if 'body' in name or 'fascia' in name: return 'Body Massager'
    return 'Others'

df_sales['Category'] = df_sales['Stock Name'].apply(extract_category)

# 4.2 处理 Stock Data
df_stock = df_stock_raw.copy()

# 【关键修改】：只提取最新一天的库存快照日期
if not df_stock.empty and 'Date' in df_stock.columns:
    # 转换为日期格式确保排序正确
    df_stock['Date'] = pd.to_datetime(df_stock['Date'])
    # 找到数据库里最新的库存日期
    latest_stock_date = df_stock['Date'].max()
    # 核心过滤：只保留最新一天的库存数据
    df_stock = df_stock[df_stock['Date'] == latest_stock_date]
    # 在侧边栏显示当前是哪一天的库存
    st.sidebar.info(f"Inventory Updated: {latest_stock_date.strftime('%Y-%m-%d')}")

# 确保 Warehouse Type 存在 (保持原有逻辑)
if 'Warehouse Type' not in df_stock.columns:
    df_stock['Warehouse Type'] = 'Unknown'
else:
    df_stock['Warehouse Type'] = df_stock['Warehouse Type'].fillna('Unknown')

# --- 统一数据预计算 (确保侧边栏导出按钮能找到这些变量) ---

# 1. 计算库存汇总 (用于 Tab 1 和 PDF 导出)
df_stock_positive = df_stock[df_stock['Quantity'] > 0].copy()
summary_df = pd.DataFrame()
if not df_stock_positive.empty:
    summary_df = df_stock_positive.groupby('Warehouse Type')['Quantity'].sum().reset_index().sort_values('Quantity', ascending=False)

# 2. 计算 DOS 数据 (用于 Tab 3 和 PDF 导出)
# 注意：DOS 计算必须基于数据库最晚日期，不受过滤器影响，所以使用 df_sales_raw
last_date_all = pd.to_datetime(df_sales_raw['Date']).max()
start_date_dos = last_date_all - timedelta(days=21)
# 转换原始数据的日期类型
df_sales_for_dos = df_sales_raw.copy()
df_sales_for_dos['Date'] = pd.to_datetime(df_sales_for_dos['Date'])
recent_sales_dos = df_sales_for_dos[(df_sales_for_dos['Date'] > start_date_dos) & (df_sales_for_dos['Date'] <= last_date_all)]

sku_sales_dos = recent_sales_dos.groupby('Stock Code')['Quantity'].sum().reset_index()
sku_sales_dos['ADS'] = sku_sales_dos['Quantity'] / 21
sku_stock_dos = df_stock.groupby(['Stock Code', 'Stock Name'])['Quantity'].sum().reset_index()

dos_df = pd.merge(sku_stock_dos, sku_sales_dos[['Stock Code', 'ADS']], on='Stock Code', how='left').fillna(0)
dos_df['DOS (Days)'] = np.where(dos_df['ADS'] > 0, dos_df['Quantity'] / dos_df['ADS'], 9999)

def get_dos_status(row):
    stock = row['Quantity']
    ads = row['ADS']
    if stock <= 0: return "⚪ Out of Stock"
    if ads == 0: return "⚫ Dead Stock (No Sales)"
    dos = stock / ads
    if dos < 14: return "🔴 Low Stock (<14 Days)"
    elif dos > 60: return "🟡 Overstock (>60 Days)"
    else: return "🟢 Healthy (14-60 Days)"
dos_df['Status'] = dos_df.apply(get_dos_status, axis=1)

def draw_styled_table(pdf, header, data, widths):
    # 表头样式
    pdf.set_fill_color(26, 54, 104)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('helvetica', 'B', 10)
    for i, col in enumerate(header):
        pdf.cell(widths[i], 10, col, 1, 0, 'C', True)
    pdf.ln()

    # 表体样式（斑马纹）
    pdf.set_text_color(40, 40, 40)
    pdf.set_font('helvetica', '', 9)
    for i, row in enumerate(data):
        fill = (i % 2 == 0)
        if fill: pdf.set_fill_color(245, 247, 250)
        else: pdf.set_fill_color(255, 255, 255)
        
        for j, val in enumerate(row):
            pdf.cell(widths[j], 8, str(val), 1, 0, 'C', True)
        pdf.ln()

# --- 6. 侧边栏过滤器 ---
st.sidebar.title("Filters")
latest_date_in_data = df_sales['Date'].max()
first_day_of_current_month = latest_date_in_data.replace(day=1)

date_range = st.sidebar.date_input(
    "Primary Date Range", 
    value=(first_day_of_current_month.date(), latest_date_in_data.date()),
    min_value=df_sales['Date'].min().date(),
    max_value=df_sales['Date'].max().date()
)

# 【核心修复】：检查是否选择了完整的日期范围
if len(date_range) != 2:
    st.warning("Please select a start and end date to continue.")
    st.stop()  # 停止执行后续代码，直到用户选好第二个日期

# 现在可以安全地解包了
d1, d2 = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])

# --- 全局对比控制 ---
st.sidebar.divider()
enable_comparison = st.sidebar.checkbox("Enable Comparison", value=True)

comp_range = None
if enable_comparison:
    # 自动推算上一个等长周期作为默认对比值
    d1, d2 = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
    duration = (d2 - d1).days + 1
    prev_end = d1 - timedelta(days=1)
    prev_start = prev_end - timedelta(days=duration - 1)
    
    comp_range = st.sidebar.date_input(
        "Comparison Date Range",
        value=(prev_start.date(), prev_end.date()),
        key='global_comp_date'
    )

st.sidebar.divider()
with st.sidebar.expander("📄 Export PDF Report", expanded=False):
    st.write("Select sections:")

    # 使用独立的 key 来避免与主页面的组件冲突
    exp_summary = st.checkbox("Executive Summary", value=True, key="pdf_exp_summary")
    exp_stock = st.checkbox("Stock Balance", value=True, key="pdf_exp_stock")
    exp_sales = st.checkbox("Sales Analysis", value=True, key="pdf_exp_sales")
    exp_dos = st.checkbox("Purchase (DOS)", value=True, key="pdf_exp_dos")
    
    st.markdown("---")
    st.write("Filter data for the report:")
    all_warehouses_for_export = df_sales['Warehouse Name'].unique()
    selected_warehouses_for_export = st.multiselect(
        "Select Warehouses for PDF:",
        options=all_warehouses_for_export,
        default=all_warehouses_for_export,
        key='pdf_warehouse_filter' # 专属 key
    )

    if st.button("🚀 Prepare PDF Report", use_container_width=True):
        if not (exp_summary or exp_stock or exp_sales or exp_dos):
            st.warning("Please select at least one section.")
        else:
            with st.spinner("Generating full analytics report..."):
                
                # ==================================================================
                # 【核心修复】: 在所有 'if exp_...' 检查之前，准备好所有需要的数据
                # ==================================================================

                # --- 1. 准备【销售数据】(df_for_pdf) ---
                # 这是最基础的数据，后续计算会用到
                pdf_sales_mask = (
                    (df_sales['Date'] >= pd.to_datetime(date_range[0])) & 
                    (df_sales['Date'] <= pd.to_datetime(date_range[1])) &
                    (df_sales['Warehouse Name'].isin(selected_warehouses_for_export))
                )
                df_for_pdf = df_sales[pdf_sales_mask].copy()

                # --- 2. 准备【库存数据】(df_stock_for_pdf 和 summary_df_pdf) ---
                df_stock_for_pdf = df_stock[df_stock['Warehouse Name'].isin(selected_warehouses_for_export)].copy()
                
                df_stock_positive_pdf = df_stock_for_pdf[df_stock_for_pdf['Quantity'] > 0].copy()
                summary_df_pdf = pd.DataFrame()
                if not df_stock_positive_pdf.empty:
                    summary_df_pdf = df_stock_positive_pdf.groupby('Warehouse Type')['Quantity'].sum().reset_index().sort_values('Quantity', ascending=False)

                # --- 3. 准备【DOS数据】(dos_df_pdf) ---
                # 注意：DOS的销售部分使用不受日期范围影响的 df_sales_for_dos
                recent_sales_dos_pdf = df_sales_for_dos[
                    (df_sales_for_dos['Date'] > start_date_dos) & 
                    (df_sales_for_dos['Date'] <= last_date_all) &
                    (df_sales_for_dos['Warehouse Name'].isin(selected_warehouses_for_export))
                ]
                sku_sales_dos_pdf = recent_sales_dos_pdf.groupby('Stock Code')['Quantity'].sum().reset_index()
                sku_sales_dos_pdf['ADS'] = sku_sales_dos_pdf['Quantity'] / 21
                
                sku_stock_dos_pdf = df_stock_for_pdf.groupby(['Stock Code', 'Stock Name'])['Quantity'].sum().reset_index()

                dos_df_pdf = pd.merge(sku_stock_dos_pdf, sku_sales_dos_pdf[['Stock Code', 'ADS']], on='Stock Code', how='left').fillna(0)
                dos_df_pdf['DOS (Days)'] = np.where(dos_df_pdf['ADS'] > 0, dos_df_pdf['Quantity'] / dos_df_pdf['ADS'], 9999)
                dos_df_pdf['Status'] = dos_df_pdf.apply(get_dos_status, axis=1)

                # --- 数据准备全部完成 ---

                # 检查是否有数据，如果销售数据为空，可能没必要继续
                if df_for_pdf.empty and df_stock_for_pdf.empty:
                    st.sidebar.error("No data found for the selected filters. PDF cannot be generated.")
                    st.stop()

                # 基础设置
                date_str = f"{date_range[0]} to {date_range[1]}"
                pdf = SKG_Report(date_str)
                pdf.set_auto_page_break(auto=True, margin=15)

                # --- PART 1: SALES ANALYSIS (KPIs + Trend + Channel) ---
                if exp_sales:
                    pdf.add_page()
                    navy_blue = (26, 54, 104)
                    pdf.set_text_color(*navy_blue)
                    pdf.set_font('helvetica', 'B', 20)
                    pdf.cell(0, 15, "01. Sales Performance Analysis", 0, 1, 'L')
                    
                    pdf.set_draw_color(*navy_blue)
                    pdf.set_line_width(0.8)
                    pdf.line(11, pdf.get_y(), 200, pdf.get_y())
                    pdf.ln(10)

                    # --- 1. KPI 指标看板 ---
                    pdf.set_fill_color(240, 244, 248)
                    pdf.rect(10, pdf.get_y(), 190, 30, 'F') 
                    kpi_y = pdf.get_y() + 7
                    pdf.set_y(kpi_y)
                    pdf.set_x(10)
                    pdf.set_text_color(100, 100, 100)
                    pdf.set_font('helvetica', 'B', 10)
                    pdf.cell(63, 5, "TOTAL REVENUE", 0, 0, 'C')
                    pdf.cell(63, 5, "UNITS SOLD", 0, 0, 'C')
                    pdf.cell(63, 5, "AVG TICKET", 0, 1, 'C')
                    pdf.set_x(10)
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_font('helvetica', 'B', 14)
                    
                    # 使用 df_for_pdf
                    pdf.cell(63, 10, f"RM {df_for_pdf['Sales'].sum():,.2f}", 0, 0, 'C')
                    pdf.cell(63, 10, f"{df_for_pdf['Quantity'].sum():,.0f}", 0, 0, 'C')
                    avg_t = df_for_pdf['Sales'].mean() if not df_for_pdf.empty else 0
                    pdf.cell(63, 10, f"RM {avg_t:,.2f}", 0, 1, 'C')
                    pdf.set_y(kpi_y + 23)
                    pdf.ln(10)

                    # --- 2. 销售趋势与渠道分析 (并列图表/上下排版) ---
                    pdf.set_text_color(*navy_blue); pdf.set_font('helvetica', 'B', 12)
                    pdf.cell(0, 10, "MONTHLY REVENUE TREND", 0, 1, 'L')
                    
                    # 使用 df_for_pdf
                    df_trend_pdf = df_for_pdf.groupby(df_for_pdf['Date'].dt.to_period('M'))['Sales'].sum().reset_index()
                    df_trend_pdf['Date'] = df_trend_pdf['Date'].astype(str)
                    fig_s = px.line(df_trend_pdf, x='Date', y='Sales', markers=True, template="plotly_white")
                    fig_s.update_traces(line_color='#1A3668', line_width=3)
                    pdf.image(io.BytesIO(fig_s.to_image(format="png", width=1000, height=400)), x=10, w=190)
                    
                    pdf.ln(5)
                    pdf.cell(0, 10, "CHANNEL REVENUE COMPARISON", 0, 1, 'L')
                    # 使用 df_for_pdf
                    chan_df = df_for_pdf.groupby('AR Type')['Sales'].sum().reset_index().sort_values('Sales', ascending=False)
                    # 新增：渠道对比 Bar Chart
                    fig_chan = px.bar(chan_df, x='AR Type', y='Sales', text_auto='.2s', template="plotly_white")
                    fig_chan.update_traces(marker_color='#1A3668')
                    pdf.image(io.BytesIO(fig_chan.to_image(format="png", width=1000, height=400)), x=10, w=190)

                    # --- 3. 新页：Product Performance Analysis ---
                    pdf.add_page()
                    pdf.set_text_color(*navy_blue); pdf.set_font('helvetica', 'B', 16)
                    pdf.cell(0, 15, "Product Performance Analysis", 0, 1, 'L')
                    pdf.ln(5)

                    # A. Sales by Category Pie Chart
                    pdf.set_font('helvetica', 'B', 12)
                    pdf.cell(0, 10, "SALES BY CATEGORY", 0, 1, 'L')
                    # 使用 df_for_pdf
                    cat_sales_pdf = df_for_pdf.groupby('Category')['Sales'].sum().reset_index()
                    fig_cat = px.pie(cat_sales_pdf, values='Sales', names='Category', template="plotly_white", hole=0.4)
                    pdf.image(io.BytesIO(fig_cat.to_image(format="png", width=800, height=400)), x=35, w=140)
                    
                    pdf.ln(10)
                    # B. Detailed Product Performance Table
                    pdf.cell(0, 10, "TOP SELLING MODELS", 0, 1, 'L')
                    
                    # 表头
                    pdf.set_fill_color(*navy_blue); pdf.set_text_color(255, 255, 255); pdf.set_font('helvetica', 'B', 9)
                    pdf.cell(90, 10, " MODEL NAME", 1, 0, 'L', True)
                    pdf.cell(35, 10, "CATEGORY", 1, 0, 'C', True)
                    pdf.cell(25, 10, "UNITS", 1, 0, 'C', True)
                    pdf.cell(40, 10, "REVENUE ", 1, 1, 'R', True)

                    # 表体 (斑马纹)
                    pdf.set_text_color(40, 40, 40); pdf.set_font('helvetica', '', 8)
                    # 使用 df_for_pdf
                    prod_perf = df_for_pdf.groupby(['Stock Name', 'Category']).agg({'Quantity':'sum', 'Sales':'sum'}).reset_index().sort_values('Quantity', ascending=False).head(15)
                    
                    for i, row in prod_perf.iterrows():
                        fill = (i % 2 == 0)
                        pdf.set_fill_color(245, 247, 250) if fill else pdf.set_fill_color(255, 255, 255)
                        
                        p_name = str(row['Stock Name'])[:45].encode('ascii', 'ignore').decode()
                        pdf.cell(90, 8, f" {p_name}", 1, 0, 'L', fill)
                        pdf.cell(35, 8, f"{row['Category']}", 1, 0, 'C', fill)
                        pdf.cell(25, 8, f"{int(row['Quantity'])}", 1, 0, 'C', fill)
                        pdf.cell(40, 8, f"RM {row['Sales']:,.2f} ", 1, 1, 'R', fill)

                    # --- 4. 新页：Product Trend Analysis ---
                    pdf.add_page()
                    pdf.set_text_color(*navy_blue); pdf.set_font('helvetica', 'B', 16)
                    pdf.cell(0, 15, "Product Trend Analysis", 0, 1, 'L')
                    pdf.ln(5)

                    # A. 准备对比数据 (本月 vs 上月)
                    curr_month_period = pd.to_datetime(date_range[1]).to_period('M')
                    prev_month_period = curr_month_period - 1
                    
                    # 使用 df_for_pdf
                    p_curr = df_for_pdf[df_for_pdf['Date'].dt.to_period('M') == curr_month_period].groupby('Stock Name')['Quantity'].sum().reset_index().rename(columns={'Quantity':'Current'})
                    p_prev = df_for_pdf[df_for_pdf['Date'].dt.to_period('M') == prev_month_period].groupby('Stock Name')['Quantity'].sum().reset_index().rename(columns={'Quantity':'Previous'})

                    
                    perf_df = pd.merge(p_curr, p_prev, on='Stock Name', how='outer').fillna(0)
                    perf_df['Growth'] = perf_df['Current'] - perf_df['Previous']
                    
                    # 趋势对比柱状图 (Chart)
                    pdf.set_font('helvetica', 'B', 12)
                    pdf.cell(0, 10, f"MODELS PERFORMANCE TREND: {prev_month_period} vs {curr_month_period}", 0, 1, 'L')
                    top_perf_plot = perf_df.sort_values('Current', ascending=False).head(10)
                    plot_data = top_perf_plot.melt(id_vars='Stock Name', value_vars=['Previous', 'Current'], var_name='Period', value_name='Qty')
                    fig_perf = px.bar(plot_data, x='Qty', y='Stock Name', color='Period', barmode='group', orientation='h', 
                                    template="plotly_white", color_discrete_map={'Previous':'#A0AEC0', 'Current':'#1A3668'})
                    pdf.image(io.BytesIO(fig_perf.to_image(format="png", width=1000, height=500)), x=10, w=190)
                    
                    pdf.ln(10)

                    # B. 产品性能汇总表 (Detailed Zebra Table)
                    pdf.cell(0, 10, "PRODUCT PERFORMANCE SUMMARY", 0, 1, 'L')
                    
                    # 表头
                    pdf.set_fill_color(*navy_blue); pdf.set_text_color(255, 255, 255); pdf.set_font('helvetica', 'B', 9)
                    pdf.cell(100, 10, " MODEL NAME", 1, 0, 'L', True)
                    pdf.cell(25, 10, "PREV QTY", 1, 0, 'C', True)
                    pdf.cell(25, 10, "CURR QTY", 1, 0, 'C', True)
                    pdf.cell(30, 10, "GROWTH ", 1, 1, 'R', True)

                    # 表体
                    pdf.set_text_color(40, 40, 40); pdf.set_font('helvetica', '', 8)
                    display_perf = perf_df.sort_values('Current', ascending=False).head(20)
                    
                    for i, row in display_perf.iterrows():
                        fill = (i % 2 == 0)
                        pdf.set_fill_color(245, 247, 250) if fill else pdf.set_fill_color(255, 255, 255)
                        
                        p_name = str(row['Stock Name'])[:50].encode('ascii', 'ignore').decode()
                        pdf.cell(100, 8, f" {p_name}", 1, 0, 'L', fill)
                        pdf.cell(25, 8, f"{int(row['Previous'])}", 1, 0, 'C', fill)
                        pdf.cell(25, 8, f"{int(row['Current'])}", 1, 0, 'C', fill)
                        
                        # 增长逻辑颜色
                        growth_val = int(row['Growth'])
                        if growth_val > 0:
                            pdf.set_text_color(0, 128, 0) # 绿色
                            growth_str = f"+{growth_val} "
                        elif growth_val < 0:
                            pdf.set_text_color(200, 0, 0) # 红色
                            growth_str = f"{growth_val} "
                        else:
                            pdf.set_text_color(40, 40, 40)
                            growth_str = "0 "
                            
                        pdf.cell(30, 8, growth_str, 1, 1, 'R', fill)
                        pdf.set_text_color(40, 40, 40) # 还原颜色

                # --- PART 2: STOCK BALANCE (Distribution + Top 20 + Location) ---
                if exp_stock:
                    # --- 关键步骤 1: 创建专门给 PDF 使用的、经过仓库筛选的库存数据 ---
                    # df_stock 是原始的、包含所有仓库最新日期的库存数据
                    # selected_warehouses_for_export 是您在侧边栏为 PDF 创建的仓库选择器
                    df_stock_for_pdf = df_stock[df_stock['Warehouse Name'].isin(selected_warehouses_for_export)].copy()

                    # --- 关键步骤 2: 基于筛选后的库存数据，重新计算库存汇总 ---
                    df_stock_positive_pdf = df_stock_for_pdf[df_stock_for_pdf['Quantity'] > 0].copy()
                    summary_df_pdf = pd.DataFrame()
                    if not df_stock_positive_pdf.empty:
                        summary_df_pdf = df_stock_positive_pdf.groupby('Warehouse Type')['Quantity'].sum().reset_index().sort_values('Quantity', ascending=False)
                    # --- 数据准备结束 ---

                    pdf.add_page()
                    navy_blue = (26, 54, 104)
                    pdf.set_text_color(*navy_blue)
                    pdf.set_font('helvetica', 'B', 20)
                    pdf.cell(0, 15, "02. Inventory & Distribution", 0, 1, 'L')
                    
                    pdf.set_draw_color(*navy_blue)
                    pdf.set_line_width(0.8)
                    pdf.line(11, pdf.get_y(), 200, pdf.get_y())
                    pdf.ln(10)

                    # A. Stock KPI Card (库存总量看板)
                    pdf.set_fill_color(240, 244, 248)
                    pdf.rect(10, pdf.get_y(), 190, 20, 'F')
                    
                    pdf.set_y(pdf.get_y() + 5)
                    pdf.set_text_color(100, 100, 100); pdf.set_font('helvetica', 'B', 10)
                    pdf.cell(95, 5, "TOTAL STOCK QUANTITY", 0, 0, 'C')
                    pdf.cell(95, 5, "ACTIVE LOCATIONS", 0, 1, 'C')
                    
                    pdf.set_text_color(0, 0, 0); pdf.set_font('helvetica', 'B', 14)
                    # 【修改】: 使用 summary_df_pdf 和 df_stock_for_pdf
                    total_qty_st = summary_df_pdf['Quantity'].sum() if not summary_df_pdf.empty else 0
                    active_locs = df_stock_for_pdf[df_stock_for_pdf['Quantity']>0]['Warehouse Name'].nunique()
                    pdf.cell(95, 8, f"{int(total_qty_st):,}", 0, 0, 'C')
                    pdf.cell(95, 8, f"{active_locs}", 0, 1, 'C')
                    pdf.ln(10)
                    
                    # B. Distribution Pie Chart
                    pdf.set_text_color(*navy_blue); pdf.set_font('helvetica', 'B', 12)
                    pdf.cell(0, 10, "STOCK DISTRIBUTION BY TYPE", 0, 1, 'L')
                    
                    # 【修改】: 使用 summary_df_pdf
                    if not summary_df_pdf.empty:
                        fig_st = px.pie(summary_df_pdf, values='Quantity', names='Warehouse Type', template="plotly_white")
                        fig_st.update_layout(margin=dict(l=20, r=20, t=20, b=20))
                        pdf.image(io.BytesIO(fig_st.to_image(format="png", width=800, height=400)), x=55, w=100)
                    
                    # --- 库存汇总表格 (Type, Qty, % Share) ---
                    pdf.ln(5)
                    pdf.set_font('helvetica', 'B', 12)
                    pdf.cell(0, 10, "INVENTORY SUMMARY BY TYPE", 0, 1, 'L')
                    
                    # 表头 (深蓝背景，白色文字)
                    pdf.set_fill_color(*navy_blue); pdf.set_text_color(255, 255, 255)
                    pdf.set_font('helvetica', 'B', 10)
                    pdf.cell(80, 10, " WAREHOUSE TYPE", 1, 0, 'L', True)
                    pdf.cell(40, 10, "QUANTITY ", 1, 0, 'R', True)
                    pdf.cell(40, 10, "SHARE (%) ", 1, 1, 'R', True)
                    
                    # 表体 (斑马纹底色)
                    pdf.set_text_color(40, 40, 40); pdf.set_font('helvetica', '', 10)
                    # 【修改】: 使用 summary_df_pdf
                    total_q = summary_df_pdf['Quantity'].sum() if not summary_df_pdf.empty else 0
                    if not summary_df_pdf.empty:
                        for i, row in summary_df_pdf.iterrows():
                            fill = (i % 2 == 0)
                            pdf.set_fill_color(245, 247, 250) if fill else pdf.set_fill_color(255, 255, 255)
                            
                            share_val = (row['Quantity'] / total_q * 100) if total_q > 0 else 0
                            pdf.cell(80, 8, f" {row['Warehouse Type']}", 1, 0, 'L', fill)
                            pdf.cell(40, 8, f"{int(row['Quantity']):,} ", 1, 0, 'R', fill)
                            pdf.cell(40, 8, f"{share_val:.1f}% ", 1, 1, 'R', fill)

                    # C. Top 20 SKUs Bar Chart (另起一页)
                    pdf.add_page()
                    pdf.set_text_color(*navy_blue); pdf.set_font('helvetica', 'B', 14)
                    pdf.cell(0, 10, "TOP 20 SKUS BY QUANTITY", 0, 1, 'L')
                    
                    # 【修改】: 使用 df_stock_for_pdf
                    top_20_st = df_stock_for_pdf[df_stock_for_pdf['Quantity']>0].groupby('Stock Name')['Quantity'].sum().nlargest(20).reset_index().sort_values('Quantity', ascending=True)
                    if not top_20_st.empty:
                        fig_top20 = px.bar(top_20_st, x='Quantity', y='Stock Name', orientation='h', template="plotly_white")
                        fig_top20.update_traces(marker_color='#1A3668')
                        pdf.image(io.BytesIO(fig_top20.to_image(format="png", width=1000, height=600)), x=10, w=190)

                    # D. Location Details Summary Table
                    pdf.ln(10); pdf.set_font('helvetica', 'B', 12); pdf.cell(0, 10, "LOCATION DETAILS (TOP 15)", 0, 1, 'L')
                    
                    pdf.set_fill_color(*navy_blue); pdf.set_text_color(255, 255, 255); pdf.set_font('helvetica', 'B', 10)
                    pdf.cell(120, 10, " WAREHOUSE NAME", 1, 0, 'L', True)
                    pdf.cell(40, 10, "QTY BALANCE ", 1, 1, 'R', True)

                    pdf.set_text_color(40, 40, 40); pdf.set_font('helvetica', '', 9)
                    # 【修改】: 使用 df_stock_for_pdf
                    loc_df = df_stock_for_pdf[df_stock_for_pdf['Quantity']>0].groupby('Warehouse Name')['Quantity'].sum().reset_index().sort_values('Quantity', ascending=False).head(15)
                    if not loc_df.empty:
                        for i, row in loc_df.iterrows():
                            fill = (i % 2 == 0)
                            pdf.set_fill_color(245, 247, 250) if fill else pdf.set_fill_color(255, 255, 255)
                            name = str(row['Warehouse Name'])[:50].encode('ascii', 'ignore').decode()
                            pdf.cell(120, 8, f" {name}", 1, 0, 'L', fill)
                            pdf.cell(40, 8, f"{int(row['Quantity']):,} ", 1, 1, 'R', fill)

                # --- PART 3: PURCHASE (DOS Analysis) ---
                if exp_dos:
                    # --- 关键步骤 1: 为 PDF 重新计算 DOS 数据 ---
                    # 1.1 获取为 PDF 筛选过的库存数据 (df_stock_for_pdf 应该在 exp_stock 逻辑中或之前已经定义)
                    # 如果 exp_stock 没有被勾选，我们需要在这里也定义一下 df_stock_for_pdf
                    if 'df_stock_for_pdf' not in locals():
                        df_stock_for_pdf = df_stock[df_stock['Warehouse Name'].isin(selected_warehouses_for_export)].copy()

                    # 1.2 筛选与 PDF 仓库选择相关的近期销售数据
                    # df_sales_raw 是原始的、未经过滤的销售数据
                    recent_sales_dos_pdf = df_sales_for_dos[
                        (df_sales_for_dos['Date'] > start_date_dos) & 
                        (df_sales_for_dos['Date'] <= last_date_all) &
                        (df_sales_for_dos['Warehouse Name'].isin(selected_warehouses_for_export)) # <--- 应用仓库过滤器
                    ]

                    # 1.3 重新执行 DOS 计算逻辑
                    sku_sales_dos_pdf = recent_sales_dos_pdf.groupby('Stock Code')['Quantity'].sum().reset_index()
                    sku_sales_dos_pdf['ADS'] = sku_sales_dos_pdf['Quantity'] / 21
                    
                    # 使用筛选后的库存 df_stock_for_pdf
                    sku_stock_dos_pdf = df_stock_for_pdf.groupby(['Stock Code', 'Stock Name'])['Quantity'].sum().reset_index()

                    dos_df_pdf = pd.merge(sku_stock_dos_pdf, sku_sales_dos_pdf[['Stock Code', 'ADS']], on='Stock Code', how='left').fillna(0)
                    dos_df_pdf['DOS (Days)'] = np.where(dos_df_pdf['ADS'] > 0, dos_df_pdf['Quantity'] / dos_df_pdf['ADS'], 9999)
                    dos_df_pdf['Status'] = dos_df_pdf.apply(get_dos_status, axis=1)
                    # --- 数据准备结束 ---

                    pdf.add_page()
                    navy_blue = (26, 54, 104)
                    pdf.set_text_color(*navy_blue)
                    pdf.set_font('helvetica', 'B', 20)
                    pdf.cell(0, 15, "03. Purchase & DOS Analysis", ln=True)
                    
                    pdf.set_draw_color(*navy_blue)
                    pdf.set_line_width(0.8)
                    pdf.line(11, pdf.get_y(), 200, pdf.get_y())
                    pdf.ln(10)
                    
                    # A. DOS Health KPI Cards
                    # 【修改】: 使用 dos_df_pdf
                    status_counts_pdf = dos_df_pdf['Status'].value_counts()
                    pdf.set_fill_color(240, 244, 248)
                    pdf.rect(10, pdf.get_y(), 190, 20, 'F')
                    
                    pdf.set_y(pdf.get_y() + 5)
                    pdf.set_text_color(100, 100, 100); pdf.set_font('helvetica', 'B', 10)
                    pdf.cell(95, 5, "HEALTHY SKUS (14-60D)", 0, 0, 'C')
                    pdf.cell(95, 5, "LOW STOCK ALERTS", 0, 1, 'C')
                    
                    pdf.set_text_color(0, 0, 0); pdf.set_font('helvetica', 'B', 14)
                    healthy_cnt = status_counts_pdf.get('🟢 Healthy (14-60 Days)', 0)
                    low_cnt = status_counts_pdf.get('🔴 Low Stock (<14 Days)', 0)
                    pdf.cell(95, 8, f"{healthy_cnt}", 0, 0, 'C')
                    pdf.set_text_color(200, 0, 0) # 警示项用红色
                    pdf.cell(95, 8, f"{low_cnt}", 0, 1, 'C')
                    pdf.ln(10)
                    
                    # B. Detailed DOS Table
                    pdf.set_text_color(*navy_blue); pdf.set_font('helvetica', 'B', 12)
                    pdf.cell(0, 10, "INVENTORY HEALTH DETAIL (TOP 25)", 0, 1, 'L')
                    
                    # 表头
                    pdf.set_fill_color(*navy_blue); pdf.set_text_color(255, 255, 255); pdf.set_font('helvetica', 'B', 10)
                    pdf.cell(90, 10, " MODEL NAME", 1, 0, 'L', True)
                    pdf.cell(50, 10, "STATUS", 1, 0, 'C', True)
                    pdf.cell(30, 10, "DOS DAYS ", 1, 1, 'R', True)
                    
                    # 表体
                    pdf.set_text_color(40, 40, 40); pdf.set_font('helvetica', '', 8)
                    # 【修改】: 使用 dos_df_pdf
                    if not dos_df_pdf.empty:
                        for i, row in dos_df_pdf.sort_values('DOS (Days)').head(25).iterrows():
                            fill = (i % 2 == 0)
                            pdf.set_fill_color(245, 247, 250) if fill else pdf.set_fill_color(255, 255, 255)
                            
                            name = str(row['Stock Name'])[:45].encode('ascii', 'ignore').decode()
                            status_txt = str(row['Status']).encode('ascii', 'ignore').decode()
                            
                            pdf.cell(90, 8, f" {name}", 1, 0, 'L', fill)
                            # 状态列根据健康度加粗显示
                            if "Low Stock" in status_txt:
                                pdf.set_text_color(200, 0, 0)
                            elif "Healthy" in status_txt:
                                pdf.set_text_color(0, 128, 0)
                            
                            pdf.cell(50, 8, f"{status_txt}", 1, 0, 'C', fill)
                            pdf.set_text_color(40, 40, 40) # 还原颜色
                            pdf.cell(30, 8, f"{row['DOS (Days)']:,.1f} ", 1, 1, 'R', fill)

                # 输出与下载
                pdf_output = pdf.output()
                st.sidebar.success("✅ Full Report Ready!")
                st.sidebar.download_button(
                    label="📥 Click to Download PDF",
                    data=bytes(pdf_output),
                    file_name=f"SKG_Full_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

# --- 6. 主面板 ---
st.title("SKG Business Analytics")

# 1. 定义仓库过滤器 (可以放在一个展开容器里，也可以直接放在主区域)
with st.expander("🔎 Filter by Warehouse", expanded=False):
    all_warehouses = df_sales['Warehouse Name'].unique()
    selected_warehouses_sales = st.multiselect(
        "Select Warehouses:",
        options=all_warehouses,
        default=all_warehouses,
        key='sales_warehouse_filter'
    )

# 2. 应用所有过滤器（日期和仓库）
mask_curr = (
    (df_sales['Date'] >= pd.to_datetime(date_range[0])) & 
    (df_sales['Date'] <= pd.to_datetime(date_range[1])) &
    (df_sales['Warehouse Name'].isin(selected_warehouses_sales))
)
df_curr = df_sales[mask_curr].copy()

tab1, tab2, tab3 = st.tabs(["📦 Stock Balance", "📈 Sales Analysis", "🛒 Purchase (DOS)"])

# === TAB 1: STOCK ===
with tab1:
    st.header("Inventory Overview")
    
    # --- 1. 数据预处理 (核心要求：仅呈现 > 0 的数据) ---
    df_stock_positive = df_stock[df_stock['Quantity'] > 0].copy()

    if df_stock_positive.empty:
        st.warning("No active stock balance (>0) found.")
    else:
        total_qty = summary_df['Quantity'].sum()
        summary_df['% Share'] = (summary_df['Quantity'] / total_qty * 100).apply(lambda x: f"{x:.1f}%")
        
        col_pie, col_spacer, col_table = st.columns([1, 0.2, 1]) 
        
        with col_pie:
            st.subheader("Distribution")
            fig_pie = px.pie(summary_df, values='Quantity', names='Warehouse Type', hole=0.5)
            fig_pie.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=300)
            st.plotly_chart(fig_pie, use_container_width=True)

        s_max = summary_df['Quantity'].max()
        safe_s_max = int(s_max) if pd.notna(s_max) and s_max > 0 else 100

        with col_table:
            st.subheader("Balance Summary")
            st.metric(label="Total Active Stock (Qty > 0)", value=f"{total_qty:,.0f}")
            st.dataframe(
                summary_df,
                hide_index=True,
                use_container_width=True,
                height=300,
                column_config={
                    "Warehouse Type": "Type",
                    "Quantity": st.column_config.ProgressColumn(
                        "Stock Qty", format="%d", min_value=0, max_value=safe_s_max
                    )
                }
            )

        st.divider()

        # --- 3. Top 20 SKUs (增加 Filter Button) ---
        st.subheader("Top 20 SKUs Analysis")
        
        # 定义分类按钮
        stock_filter = st.pills(
            "Quick Filter:",
            options=["All", "Warehouse", "Consign", "Warehouse and Consign"],
            selection_mode="single",
            default="All"
        )

        # 执行过滤逻辑 (使用你打印出来的全大写字符串)
        if stock_filter == "Warehouse":
            # 匹配数据库中的 "WAREHOUSE"
            display_stock = df_stock_positive[df_stock_positive['Warehouse Type'] == 'WAREHOUSE']
        elif stock_filter == "Consign":
            # 匹配数据库中的 "CONSIGN"
            display_stock = df_stock_positive[df_stock_positive['Warehouse Type'] == 'CONSIGN']
        elif stock_filter == "Warehouse and Consign":
            # 同时包含全大写的两类
            display_stock = df_stock_positive[df_stock_positive['Warehouse Type'].isin(['WAREHOUSE', 'CONSIGN'])]
        else:
            # "All" 选项
            display_stock = df_stock_positive

        # 检查过滤后是否为空
        if display_stock.empty:
            st.info(f"No stock found for: {stock_filter} (Check if the Type is correct in Master Data)")
        else:
            top_stock = display_stock.groupby('Stock Name')['Quantity'].sum().nlargest(20).reset_index().sort_values('Quantity', ascending=True)
            fig_bar = px.bar(top_stock, x='Quantity', y='Stock Name', orientation='h', text_auto=True, color='Quantity', color_continuous_scale='Blues')
            fig_bar.update_layout(height=600, yaxis_title=None)
            st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()

        # --- 4. Location Details (点击行显示明细) ---
        st.subheader(f"Location Details ({stock_filter})")
        st.caption("✨ Tip: Click any row below to see product details.")

        # 根据当前选中的 filter 决定显示的 card
        active_types = display_stock.groupby('Warehouse Type')['Quantity'].sum().sort_values(ascending=False).index.tolist()
        grid_cols = st.columns(3)
        
        for i, wh_type in enumerate(active_types):
            type_data = display_stock[display_stock['Warehouse Type'] == wh_type]
            breakdown = type_data.groupby('Warehouse Name')['Quantity'].sum().reset_index().sort_values('Quantity', ascending=False)
            
            # 【这里是修复代码：计算安全的最大值】
            # 先拿最大值
            q_max = breakdown['Quantity'].max()
            # 检查：如果是空的(NaN)或者小于等于0，就默认设为100，否则转为整数
            safe_max = int(q_max) if pd.notna(q_max) and q_max > 0 else 100
            
            with grid_cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"**{wh_type}**")
                    
                    # 渲染表格
                    event = st.dataframe(
                        breakdown,
                        hide_index=True,
                        use_container_width=True,
                        height=280,
                        on_select="rerun",           
                        selection_mode="single-row",
                        key=f"df_{wh_type}",         
                        column_config={
                            "Quantity": st.column_config.ProgressColumn(
                                "Qty", 
                                format="%d", 
                                min_value=0, 
                                max_value=safe_max # <--- 这里改用了算好的 safe_max
                            )
                        }
                    )
                    
                    # 点击交互明细 (保持不变)
                    if event and event.selection.rows:
                        selected_index = event.selection.rows[0]
                        selected_loc = breakdown.iloc[selected_index]['Warehouse Name']
                        
                        st.markdown(f"---")
                        st.markdown(f"📦 **{selected_loc}** Breakdown:")
                        prod_detail = type_data[type_data['Warehouse Name'] == selected_loc][['Stock Name', 'Quantity']]
                        st.dataframe(
                            prod_detail.sort_values('Quantity', ascending=False),
                            hide_index=True, use_container_width=True, height=180
                        )

# === TAB 2: SALES ===
with tab2:
    st.header("Sales Performance Analysis")
    
    # --- 1. 顶部变量初始化 (核心修复：防止 NameError) ---
    all_range_dates = []
    df_trend_base = pd.DataFrame()
    sorted_months_list = []

    # D. 全局对比数据准备 (用于 Section 3)
    df_comp_sidebar = pd.DataFrame()
    if enable_comparison and comp_range and len(comp_range) == 2:
        mask_comp = (
            (df_sales['Date'] >= pd.to_datetime(comp_range[0])) & 
            (df_sales['Date'] <= pd.to_datetime(comp_range[1])) &
            (df_sales['Warehouse Name'].isin(selected_warehouses_sales))
        )
        df_comp_sidebar = df_sales[mask_comp].copy()

    # E. 合并侧边栏选中的数据用于 Section 3 柱状图
    df_all_chan = pd.concat([df_comp_sidebar, df_curr], ignore_index=True)
    if not df_all_chan.empty:
        df_all_chan['Month'] = df_all_chan['Date'].dt.to_period('M').astype(str)
        sorted_months_chan = sorted(df_all_chan['Month'].unique())
    
    # --- 4. 渲染逻辑 ---
    if df_curr.empty:
        st.warning("No sales data found for the primary selected range.")
    else:
        # =========================================================
        # PART 1: KPI Summary (仅显示当前周期)
        # =========================================================
        total_sales = df_curr['Sales'].sum()
        total_qty = df_curr['Quantity'].sum()
        avg_order = total_sales / len(df_curr) if len(df_curr) > 0 else 0
        
        k1, k2, k3 = st.columns(3)
        k1.metric("💰 Total Revenue", f"RM{total_sales:,.2f}")
        k2.metric("📦 Units Sold", f"{total_qty:,.0f}")
        k3.metric("🧾 Avg. Ticket Size", f"RM{avg_order:,.2f}")
        
        st.divider()

        # =========================================================
        # PART 2: Overall Company Trend (仅显示当前周期)
        # =========================================================
        st.subheader("1. Overall Company Trend")
        trend_view = st.radio("Time Grouping:", ["Monthly", "Weekly"], horizontal=True, key='trend_view_radio')
        freq = 'M' if trend_view == "Monthly" else 'W'
        
        trend_df = df_curr.copy()
        trend_df['Sort_Key'] = trend_df['Date'].dt.to_period(freq).dt.start_time
        trend_df['DP'] = trend_df['Date'].dt.to_period(freq).astype(str)
        trend_data = trend_df.groupby(['Sort_Key', 'DP'])['Sales'].sum().reset_index().sort_values('Sort_Key')
        
        fig_overall = px.line(trend_data, x='DP', y='Sales', markers=True, text='Sales')
        fig_overall.update_traces(textposition="top center", texttemplate='%{text:.2s}', line_color='#1f77b4', line_width=3)
        fig_overall.update_layout(height=350, xaxis_title="Time Period", yaxis_title="Revenue (RM)")
        st.plotly_chart(fig_overall, use_container_width=True)

        st.divider()

        # =========================================================
        # PART 3: Warehouse Comparison (Section 2)
        # =========================================================
        st.subheader("2. Warehouse Comparison Breakdown")
        
        wh_comp_df = trend_df.groupby(['Sort_Key', 'DP', 'Warehouse Name'])['Sales'].sum().reset_index().sort_values('Sort_Key')
        period_order = trend_data['DP'].unique()

        # 定义一个符合图片风格的配色方案 (也可根据需要调整)
        custom_colors = ['#1A3668', '#2CA02C', '#D62728', '#E377C2', '#17BECF', '#BCBD22', '#7F7F7F']

        # 图表选择器：增加了 "Professional Line (Optimized)" 选项
        chart_type = st.selectbox(
            "Select Visualization Style:", 
            ["Professional Line (Optimized)", "Heatmap (Best for Overview)", "Small Charts (Best for Individual Trend)"], 
            index=0, 
            key='wh_view_select'
        )

        if chart_type == "Professional Line (Optimized)":
            fig_wh = px.line(
                wh_comp_df, 
                x='DP', 
                y='Sales', 
                color='Warehouse Name', 
                category_orders={"DP": period_order},
                color_discrete_sequence=custom_colors,
                template="plotly_white"
            )
            
            # 优化线条和悬停效果
            fig_wh.update_traces(
                line_width=2.5, 
                mode='lines', # 【关键修复】：使用 mode='lines' 替代 markers=False
                hovertemplate="Warehouse: %{fullData.name}<br>Revenue: RM%{y:,.2f}<extra></extra>"
            )

            # 优化布局配置
            fig_wh.update_layout(
                hovermode='x unified', 
                height=500,
                xaxis=dict(
                    title="",
                    showgrid=False,
                    linecolor='#d6d6d6'
                ),
                yaxis=dict(
                    title="Revenue (RM)",
                    showgrid=True,
                    gridcolor='#f0f0f0', 
                    tickformat=".2s",    
                    linecolor='#d6d6d6'
                ),
                legend=dict(
                    orientation="h",     
                    yanchor="bottom",
                    y=-0.25,             
                    xanchor="center",
                    x=0.5,
                    title=""
                ),
                margin=dict(t=20, b=100, l=40, r=40)
            )
            st.plotly_chart(fig_wh, use_container_width=True)

        elif chart_type == "Heatmap (Best for Overview)":
            fig_wh = px.density_heatmap(wh_comp_df, x='DP', y='Warehouse Name', z='Sales', histfunc="sum", color_continuous_scale="Viridis", text_auto=True)
            fig_wh.update_layout(xaxis=dict(type='category', categoryorder='array', categoryarray=period_order), height=500)
            st.plotly_chart(fig_wh, use_container_width=True)
            
        else: # Small Charts (Best for Individual Trend)
            fig_wh = px.line(wh_comp_df, x='DP', y='Sales', color='Warehouse Name', facet_col='Warehouse Name', facet_col_wrap=3, markers=True)
            fig_wh.update_yaxes(matches=None)
            fig_wh.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
            st.plotly_chart(fig_wh, use_container_width=True)

        st.divider()

        # =========================================================
        # PART 4: Channel & Customer Analysis (Section 3 - 支持多月份对比)
        # =========================================================
        st.subheader("3. Channel & Customer Analysis")
        ar_col1, col_spacer, ar_col2 = st.columns([1, 0.1, 1])
        
        with ar_col1:
            st.caption("📊 Monthly Revenue Breakdown by Channel (Comparison Mode)")
            chan_data = df_all_chan.groupby(['AR Type', 'Month'])['Sales'].sum().reset_index()
            fig_ar = px.bar(chan_data, x='AR Type', y='Sales', color='Month', barmode='group', text_auto='.2s', category_orders={"Month": sorted_months_chan}, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_ar.update_layout(height=450, legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig_ar, use_container_width=True)
                    
        with ar_col2:
            st.caption("🏆 Top Customers Analysis")
            
            # 1. 格式化日期字符串作为表头
            # 主日期格式: "2023-10-01 ~ 2023-10-31"
            p_label = f"{date_range[0].strftime('%Y-%m-%d')} to {date_range[1].strftime('%Y-%m-%d')}"
            
            if not enable_comparison or df_comp_sidebar.empty:
                # --- 情况 A: 正常模式 ---
                cust_detail = df_curr.groupby(['AR Type', 'AR Name'])['Sales'].sum().reset_index()
                cust_detail = cust_detail.sort_values('Sales', ascending=False).head(50)
                
                st.dataframe(
                    cust_detail, 
                    hide_index=True, 
                    use_container_width=True, 
                    height=400,
                    column_config={
                        "Sales": st.column_config.NumberColumn(p_label, format="RM%.2f")
                    }
                )
            else:
                # --- 情况 B: 对比模式 ---
                # 对比日期格式
                c_label = f"{comp_range[0].strftime('%Y-%m-%d')} to {comp_range[1].strftime('%Y-%m-%d')}"
                
                # 汇总数据
                p_sales = df_curr.groupby(['AR Type', 'AR Name'])['Sales'].sum().reset_index().rename(columns={'Sales': p_label})
                c_sales = df_comp_sidebar.groupby(['AR Type', 'AR Name'])['Sales'].sum().reset_index().rename(columns={'Sales': c_label})
                
                # 合并
                cust_detail = pd.merge(p_sales, c_sales, on=['AR Type', 'AR Name'], how='outer').fillna(0)
                cust_detail['Diff'] = cust_detail[p_label] - cust_detail[c_label]
                
                # 排序：按主日期销量排序
                cust_detail = cust_detail.sort_values(p_label, ascending=False).head(50)
                
                st.dataframe(
                    cust_detail,
                    hide_index=True,
                    use_container_width=True,
                    height=400,
                    column_config={
                        p_label: st.column_config.NumberColumn(p_label, format="RM%.2f"),
                        c_label: st.column_config.NumberColumn(c_label, format="RM%.2f"),
                        "Diff": st.column_config.NumberColumn("Difference", format="RM%.2f")
                    }
                )

        st.subheader("3.1 Detailed Customer & Product Breakdown")
        st.caption("💡 备注：此表仅显示【主日期范围】的数据。")

        dd_col1, dd_col2, dd_col3 = st.columns(3)

        # --- 第一层：AR Type ---
        with dd_col1:
            st.markdown("**Step 1: Select AR Type**")
            # 这里的列表顺序决定了默认显示顺序：Quantity 在 Sales 之前
            type_summary = df_curr.groupby('AR Type')[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)
            
            event_type = st.dataframe(
                type_summary,
                hide_index=True,
                use_container_width=True,
                height=300,
                on_select="rerun",
                selection_mode="single-row",
                key="dd_type_table",
                column_config={
                    "AR Type": st.column_config.TextColumn("Channel Type"),
                    "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                    "Sales": st.column_config.NumberColumn("Total Sales", format="RM%.2f")
                }
            )

        # --- 第二层：AR Name ---
        selected_type = None
        if event_type and event_type.selection.rows:
            selected_index = event_type.selection.rows[0]
            selected_type = type_summary.iloc[selected_index]['AR Type']

        with dd_col2:
            st.markdown(f"**Step 2: Customers in {selected_type if selected_type else '...'}**")
            if selected_type:
                name_summary = df_curr[df_curr['AR Type'] == selected_type].groupby('AR Name')[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)
                
                event_name = st.dataframe(
                    name_summary,
                    hide_index=True,
                    use_container_width=True,
                    height=300,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="dd_name_table",
                    column_config={
                        "AR Name": st.column_config.TextColumn("Customer Name"),
                        "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                        "Sales": st.column_config.NumberColumn("Sales", format="RM%.2f")
                    }
                )
            else:
                st.info("Please select an AR Type.")

        # --- 第三层：Product ---
        selected_name = None
        if selected_type and 'event_name' in locals() and event_name and event_name.selection.rows:
            selected_index_name = event_name.selection.rows[0]
            selected_name = name_summary.iloc[selected_index_name]['AR Name']

        with dd_col3:
            st.markdown(f"**Step 3: Products for {selected_name if selected_name else '...'}**")
            if selected_name:
                product_summary = df_curr[
                    (df_curr['AR Type'] == selected_type) & 
                    (df_curr['AR Name'] == selected_name)
                ].groupby('Stock Name')[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)
                
                st.dataframe(
                    product_summary,
                    hide_index=True,
                    use_container_width=True,
                    height=300,
                    column_config={
                        "Stock Name": st.column_config.TextColumn("Model Name"),
                        "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                        "Sales": st.column_config.NumberColumn("Sales", format="RM%.2f")
                    }
                )
            else:
                st.info("Please select a Customer.")

        st.divider()
        
        # =========================================================
        # PART 5: Product Performance & Sparklines (Section 4)
        # =========================================================
        st.subheader("4. Product Performance & Trend Analysis")
        
        # --- A. 获取“当月”和“上月”的周期 ---
        curr_month_period = pd.to_datetime(date_range[1]).to_period('M')
        prev_month_period = curr_month_period - 1

        # --- B. 准备快照数据 (饼图和 Top 5) ---
        p_top_col1, col_spacer_p, p_top_col2 = st.columns([1, 0.1, 1])
        with p_top_col1:
            st.caption(f"📊 Sales by Category ({curr_month_period})")
            cat_sales = df_sales[
                (df_sales['Date'].dt.to_period('M') == curr_month_period) & 
                (df_sales['Warehouse Name'].isin(selected_warehouses_sales))
            ].groupby('Category')['Sales'].sum().reset_index().sort_values('Sales', ascending=False)
            fig_cat = px.pie(cat_sales, values='Sales', names='Category', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_cat.update_layout(height=350, margin=dict(t=30, b=0, l=0, r=0))
            st.plotly_chart(fig_cat, use_container_width=True)


        with p_top_col2:
            st.caption(f"🏆 Top Selling Models ({curr_month_period})")
            
            # 1. 先生成 top_m 数据
            top_m = df_sales[
                (df_sales['Date'].dt.to_period('M') == curr_month_period) & 
                (df_sales['Warehouse Name'].isin(selected_warehouses_sales))
            ].groupby(['Stock Name', 'Category'])[['Quantity', 'Sales']].sum().reset_index().sort_values('Quantity', ascending=False).head(5)
            
            # 2. 生成数据后再计算安全的最大值
            t_max = top_m['Quantity'].max()
            safe_t_max = int(t_max) if pd.notna(t_max) and t_max > 0 else 100

            # 3. 渲染表格
            if not top_m.empty:
                st.dataframe(
                    top_m[['Stock Name', 'Category', 'Quantity', 'Sales']], 
                    use_container_width=True, hide_index=True, height=250, 
                    column_config={
                        "Category": st.column_config.TextColumn("Category", width="small"), 
                        "Stock Name": st.column_config.TextColumn("Model Name", width="medium"), 
                        "Quantity": st.column_config.ProgressColumn(
                            "Units", format="%d", min_value=0, max_value=safe_t_max # 使用算好的安全值
                        ),
                        "Sales": st.column_config.NumberColumn(format="RM%.2f")
                    }
                )

        # =========================================================
        # PART 5.1: Product-to-Customer Drill-down (仅跟随主日期)
        # =========================================================
        st.markdown("---")
        st.subheader("🔍 Product Sales Traceability")
        st.caption("💡 备注：此表仅显示【主日期范围】的数据。")

        p_col1, p_col2, p_col3 = st.columns(3)

        # --- 第一层：Stock Name (Model) ---
        with p_col1:
            st.markdown("**Step 1: Select Model**")
            # 汇总 Units (Quantity) 和 Sales
            model_summary = df_curr.groupby('Stock Name')[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)
            
            event_model = st.dataframe(
                model_summary,
                hide_index=True,
                use_container_width=True,
                height=400,
                on_select="rerun",
                selection_mode="single-row",
                key="dr_model_table",
                column_config={
                    "Stock Name": st.column_config.TextColumn("Model Name"),
                    "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                    "Sales": st.column_config.NumberColumn("Total Sales", format="RM%.2f")
                }
            )

        # --- 第二层：AR Type ---
        selected_model = None
        if event_model and event_model.selection.rows:
            selected_index = event_model.selection.rows[0]
            selected_model = model_summary.iloc[selected_index]['Stock Name']

        with p_col2:
            st.markdown(f"**Step 2: Channels for {selected_model if selected_model else '...'}**")
            if selected_model:
                # 过滤并汇总 Units 和 Sales
                type_summary = df_curr[df_curr['Stock Name'] == selected_model].groupby('AR Type')[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)
                
                event_type_p = st.dataframe(
                    type_summary,
                    hide_index=True,
                    use_container_width=True,
                    height=400,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="dr_type_p_table",
                    column_config={
                        "AR Type": st.column_config.TextColumn("Channel Type"),
                        "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                        "Sales": st.column_config.NumberColumn("Sales", format="RM%.2f")
                    }
                )
            else:
                st.info("Please select a Model.")

        # --- 第三层：AR Name ---
        selected_type_p = None
        if selected_model and 'event_type_p' in locals() and event_type_p and event_type_p.selection.rows:
            selected_index_type = event_type_p.selection.rows[0]
            selected_type_p = type_summary.iloc[selected_index_type]['AR Type']

        with p_col3:
            st.markdown(f"**Step 3: Customers ( {selected_type_p if selected_type_p else '...'} )**")
            if selected_type_p:
                # 过滤并汇总 Units 和 Sales
                customer_summary = df_curr[
                    (df_curr['Stock Name'] == selected_model) & 
                    (df_curr['AR Type'] == selected_type_p)
                ].groupby('AR Name')[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)
                
                st.dataframe(
                    customer_summary,
                    hide_index=True,
                    use_container_width=True,
                    height=400,
                    column_config={
                        "AR Name": st.column_config.TextColumn("Customer Name"),
                        "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                        "Sales": st.column_config.NumberColumn("Customer Sales", format="RM%.2f")
                    }
                )
            else:
                st.info("Please select a Channel Type.")

        st.divider()

        # --- C. 下层：迷你趋势线表格 (优化全量历史趋势) ---
        st.caption("📈 Top 20 Models Performance with Sparklines")
        
        # 1. 准备【不受过滤影响】的趋势线列表
        df_full_history = df_sales[
            (df_sales['Date'].dt.to_period('M') <= curr_month_period) & 
            (df_sales['Warehouse Name'].isin(selected_warehouses_sales))
        ].copy()
        df_full_history['Month_Label'] = df_full_history['Date'].dt.to_period('M').astype(str)
        
        full_months_axis = sorted(df_full_history['Month_Label'].unique())
        
        spark_raw = df_full_history.groupby(['Stock Name', 'Month_Label'])['Quantity'].sum().reset_index()
        spark_pivot = spark_raw.pivot(index='Stock Name', columns='Month_Label', values='Quantity').fillna(0)
        
        # 核心：确保趋势数据包含了完整的历史月份轴
        spark_pivot['Trend'] = spark_pivot.values.tolist()
        spark_pivot = spark_pivot.reset_index()

        # 2. 计算本月和上月 Qty
        p_curr = df_sales[
            (df_sales['Date'].dt.to_period('M') == curr_month_period) & 
            (df_sales['Warehouse Name'].isin(selected_warehouses_sales))
        ].groupby('Stock Name')['Quantity'].sum().reset_index().rename(columns={'Quantity':'Current'})

        p_prev = df_sales[
            (df_sales['Date'].dt.to_period('M') == prev_month_period) & 
            (df_sales['Warehouse Name'].isin(selected_warehouses_sales))
        ].groupby('Stock Name')['Quantity'].sum().reset_index().rename(columns={'Quantity':'Previous'})
        
        # 3. 合并数据并重新排列列顺序
        final_table = pd.merge(p_curr, p_prev, on='Stock Name', how='left').fillna(0)
        final_table = pd.merge(final_table, spark_pivot[['Stock Name', 'Trend']], on='Stock Name', how='left')
        
        # 计算增长率
        final_table['Growth %'] = ((final_table['Current'] - final_table['Previous']) / final_table['Previous'] * 100).replace([np.inf, -np.inf], 0)

        # 【关键修改】：按照你要求的顺序排列 DataFrame 列
        # 顺序：Model Name (Stock Name) -> Current -> Previous -> Growth % -> Trend
        order_columns = ['Stock Name', 'Current', 'Previous', 'Growth %', 'Trend']
        display_df = final_table.sort_values('Current', ascending=False).head(20)[order_columns]

        # --- D. 定义高亮函数 ---
        def color_growth(val):
            if val < 0:
                return 'color: #ff4b4b; font-weight: bold;' # 红色
            elif val > 0:
                return 'color: #09ab3b; font-weight: bold;' # 绿色
            return 'color: gray;'

        # 应用样式
        styled_df = display_df.style.map(color_growth, subset=['Growth %'])

        # 4. 渲染表格
        st.data_editor(
            styled_df,
            use_container_width=True, hide_index=True, height=800,
            column_config={
                "Stock Name": st.column_config.TextColumn("Model Name", width="medium"),
                "Current": st.column_config.NumberColumn(f"Qty ({curr_month_period})", format="%d"),
                "Previous": st.column_config.NumberColumn(f"Qty ({prev_month_period})", format="%d"),
                "Growth %": st.column_config.NumberColumn("Growth", format="%.1f%%"),
                "Trend": st.column_config.AreaChartColumn(
                    "Full History Trend", 
                    width="medium",
                    y_min=0, 
                    help=f"Continuous trend from {full_months_axis[0]} up to {curr_month_period}"
                )
            },
            disabled=True 
        )

# === TAB 3: DOS (Purchase) ===
with tab3:
    st.header("Inventory Health & DOS Analysis")
    st.markdown("💡 **Logic**: `DOS = Current Stock / Average Daily Sales (Past 21 Days)`")

    # --- 3. 顶部 KPI 指标 (Summary Metrics) ---
    status_counts = dos_df['Status'].value_counts()
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("🔴 Restock Needed", f"{status_counts.get('🔴 Low Stock (<14 Days)', 0)} SKUs")
    with m2:
        st.metric("🟢 Healthy Stock", f"{status_counts.get('🟢 Healthy (14-60 Days)', 0)} SKUs")
    with m3:
        st.metric("🟡 Overstock Alert", f"{status_counts.get('🟡 Overstock (>60 Days)', 0)} SKUs")
    with m4:
        st.metric("⚫ Dead Stock", f"{status_counts.get('⚫ Dead Stock (No Sales)', 0)} SKUs")

    st.divider()

    # --- 4. 过滤器 (全宽) ---
    # 修改：直接写 st.multiselect，不放在 columns 里，这样它就会自动拉宽到由左至右
    filter_status = st.multiselect(
        "Filter by Health Status:",
        options=["🔴 Low Stock (<14 Days)", "🟢 Healthy (14-60 Days)", "🟡 Overstock (>60 Days)", "⚫ Dead Stock (No Sales)", "⚪ Out of Stock"],
        default=["🔴 Low Stock (<14 Days)", "🟢 Healthy (14-60 Days)", "🟡 Overstock (>60 Days)", "⚫ Dead Stock (No Sales)", "⚪ Out of Stock"] 
    )
    
    # 过滤数据
    if filter_status:
        view_df = dos_df[dos_df['Status'].isin(filter_status)]
    else:
        view_df = dos_df 

    # 排序优化
    view_df = view_df.sort_values(by=['DOS (Days)', 'ADS'], ascending=[True, False])

    # --- 5. 详细表格 (变长) ---
    st.subheader("Detailed DOS Table")
    
    # 修改：增加了 height=800，让表格变得很长
    st.dataframe(
        view_df[['Status', 'Stock Name', 'Quantity', 'ADS', 'DOS (Days)']],
        use_container_width=True,
        hide_index=True,
        height=800,  # <--- 这里控制高度，800像素大概能显示 20-25 行
        column_config={
            "Status": st.column_config.TextColumn("Health Status", width="medium"),
            "Stock Name": st.column_config.TextColumn("Product Name", width="large"),
            "Quantity": st.column_config.NumberColumn("Current Stock", format="%d"),
            "ADS": st.column_config.NumberColumn("Avg Daily Sales", format="%.2f"),
            "DOS (Days)": st.column_config.NumberColumn(
                "Est. Days Left", 
                format="%.1f"
            )
        }
    )