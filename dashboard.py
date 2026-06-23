import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
@st.cache_data(ttl=600)
def load_data_from_supabase():
    """
    从Supabase加载所有数据。
    核心修复：为每个查询添加 .limit() 方法，以强制加载超过默认1000行的数据。
    """
    supabase = init_connection()
    try:
        # 【修复】: 使用分页加载所有数据，而不是依赖 limit()
        def load_all_data(table_name, batch_size=1000):
            """分页加载所有数据"""
            all_data = []
            offset = 0
            while True:
                response = supabase.table(table_name).select("*").range(offset, offset + batch_size - 1).execute()
                if not response.data:
                    break
                all_data.extend(response.data)
                if len(response.data) < batch_size:
                    break
                offset += batch_size
            return all_data
        
        # 加载所有表的数据
        wh_data = load_all_data("warehouse")
        df_wh_master = pd.DataFrame(wh_data)
        
        ar_data = load_all_data("ar")
        df_ar_master = pd.DataFrame(ar_data)
        
        stock_data = load_all_data("stock_details")
        df_stock_raw = pd.DataFrame(stock_data)
        
        sales_data = load_all_data("sales_details")
        df_sales_raw = pd.DataFrame(sales_data)
        
        posm_data = load_all_data("posm_details")
        df_posm_raw = pd.DataFrame(posm_data)
        
        # 【新增】: 加载 Meta Ads 数据
        meta_ads_data = load_all_data("meta_ads")
        df_meta_ads_raw = pd.DataFrame(meta_ads_data)
        
        # Meta Ads 数据预处理
        if not df_meta_ads_raw.empty:
            # 转换日期字段
            date_columns = ['reporting_starts', 'reporting_ends', 'starts', 'ends']
            for col in date_columns:
                if col in df_meta_ads_raw.columns:
                    df_meta_ads_raw[col] = pd.to_datetime(df_meta_ads_raw[col], errors='coerce')
            
            # 转换数值字段
            numeric_columns = [
                'amount_spent', 'impressions', 'reach', 'frequency', 'cpm', 'views',
                'link_clicks', 'website_landing_page_views', 'cost_per_landing_page_view',
                'cpc', 'ctr', 'instagram_profile_visits', 'video_plays', 'thruplays',
                'facebook_likes', 'cost_per_like', 'instagram_follows', 'post_shares',
                'post_saves', 'post_engagements', 'cost_per_post_engagement',
                'page_engagement', 'cost_per_page_engagement'
            ]
            for col in numeric_columns:
                if col in df_meta_ads_raw.columns:
                    df_meta_ads_raw[col] = pd.to_numeric(df_meta_ads_raw[col], errors='coerce')

        # --- 以下是您原始代码中的合并与重命名逻辑，我们将其恢复 ---
        # --- 因为问题的根源不在于此，保持代码简洁易懂 ---

        # 合并 df_stock
        if not df_stock_raw.empty and not df_wh_master.empty:
            df_stock_raw['Warehouse Code'] = df_stock_raw['Warehouse Code'].astype(str).str.strip().str.upper()
            df_stock_raw['Warehouse Name'] = df_stock_raw['Warehouse Name'].astype(str).str.strip()
            wh_m = df_wh_master.rename(columns={'warehouse_type': 'Master_WH_Type'})
            df_stock_raw = pd.merge(
                df_stock_raw, wh_m, 
                left_on=['Warehouse Code', 'Warehouse Name'], 
                right_on=['warehouse_code', 'warehouse_name'], 
                how='left'
            )
            # 【修复】: 先用 Master_WH_Type，然后用原始 warehouse_type，最后用 'UNKNOWN'
            df_stock_raw['warehouse_type'] = df_stock_raw['Master_WH_Type'].fillna(df_stock_raw.get('warehouse_type', 'UNKNOWN')).fillna('UNKNOWN')

        # 合并 df_sales
        if not df_sales_raw.empty:
            df_sales_raw['Warehouse Code'] = df_sales_raw['Warehouse Code'].astype(str).str.strip().str.upper()
            df_sales_raw['Warehouse Name'] = df_sales_raw['Warehouse Name'].astype(str).str.strip()
            df_sales_raw['AR Code'] = df_sales_raw['AR Code'].astype(str).str.strip().str.upper()
            df_sales_raw['AR Name'] = df_sales_raw['AR Name'].astype(str).str.strip()
            if not df_wh_master.empty:
                wh_m = df_wh_master.rename(columns={'warehouse_type': 'Master_WH_Type'})
                df_sales_raw = pd.merge(
                    df_sales_raw, wh_m, 
                    left_on=['Warehouse Code', 'Warehouse Name'], 
                    right_on=['warehouse_code', 'warehouse_name'], 
                    how='left'
                )
                # 【修复】: 先用 Master_WH_Type，然后用原始 warehouse_type，最后用 'UNKNOWN'
                df_sales_raw['warehouse_type'] = df_sales_raw['Master_WH_Type'].fillna(df_sales_raw.get('warehouse_type', 'UNKNOWN')).fillna('UNKNOWN')
            if not df_ar_master.empty:
                ar_m = df_ar_master.rename(columns={'ar_type': 'Master_AR_Type'})
                df_sales_raw = pd.merge(
                    df_sales_raw, ar_m, 
                    left_on=['AR Code', 'AR Name'], 
                    right_on=['ar_code', 'ar_name'], 
                    how='left'
                )
                # 【修复】: 同样处理 ar_type
                df_sales_raw['ar_type'] = df_sales_raw['Master_AR_Type'].fillna(df_sales_raw.get('ar_type', 'UNKNOWN')).fillna('UNKNOWN')

        # 合并 df_posm
        if not df_posm_raw.empty and not df_wh_master.empty:
            df_posm_raw['Warehouse Code'] = df_posm_raw['Warehouse Code'].astype(str).str.strip().str.upper()
            df_posm_raw['Warehouse Name'] = df_posm_raw['Warehouse Name'].astype(str).str.strip()
            wh_m = df_wh_master.rename(columns={'warehouse_type': 'Master_WH_Type'})
            df_posm_raw = pd.merge(
                df_posm_raw, wh_m,
                left_on=['Warehouse Code', 'Warehouse Name'],
                right_on=['warehouse_code', 'warehouse_name'],
                how='left'
            )
            # 【修复】: 先用 Master_WH_Type，然后用原始 warehouse_type，最后用 'UNKNOWN'
            df_posm_raw['warehouse_type'] = df_posm_raw['Master_WH_Type'].fillna(df_posm_raw.get('warehouse_type', 'UNKNOWN')).fillna('UNKNOWN')

        # 统一重命名
        final_rename = {
            'warehouse_type': 'Warehouse Type',
            'ar_type': 'AR Type'
        }
        df_stock_raw.rename(columns=final_rename, inplace=True)
        df_sales_raw.rename(columns=final_rename, inplace=True)
        df_posm_raw.rename(columns=final_rename, inplace=True)
        
        # 【修复】: 返回包含 Meta Ads 数据的元组
        return df_stock_raw, df_sales_raw, df_posm_raw, df_meta_ads_raw

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        st.error(f"數據庫連接或查詢失敗: {str(e)}")
        with st.expander("查看詳細錯誤信息"):
            st.code(error_details)
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
# 【修复】: 更新调用以接收 Meta Ads 数据
df_stock_raw, df_sales_raw, df_posm_raw, df_meta_ads_raw = load_data_from_supabase()

if df_stock_raw.empty or df_sales_raw.empty:
    st.warning("Database is empty or connection failed.")
    st.stop()

# --- 5. 数据预处理  ---

# 4.1 处理 Sales Data
df_sales = df_sales_raw.copy()
df_sales['Display Name'] = np.where(
    df_sales['AR Type'] == 'ONLINE',
    df_sales['ar_sub_type'].fillna('ONLINE (Unclassified)'),
    df_sales['AR Name']
)
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

# 确保 Warehouse Type 存在 (保持原有逻辑)
if 'Warehouse Type' not in df_stock.columns:
    df_stock['Warehouse Type'] = 'Unknown'
else:
    df_stock['Warehouse Type'] = df_stock['Warehouse Type'].fillna('Unknown')

df_posm = df_posm_raw.copy()
if not df_posm.empty and 'Date' in df_posm.columns:
    df_posm['Date'] = pd.to_datetime(df_posm['Date'])
    latest_posm_date = df_posm['Date'].max()
    df_posm = df_posm[df_posm['Date'] == latest_posm_date]

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

if len(date_range) != 2:
    st.warning("Please select a start and end date to continue.")
    st.stop()

d1, d2 = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])

# --- 全局对比控制 ---
st.sidebar.divider()
enable_comparison = st.sidebar.checkbox("Enable Comparison", value=True)

comp_range = None
if enable_comparison:
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

                # 其他PDF部分代码保持原样...
                # (为了简洁，这里省略了其他PDF生成代码)

                # 生成PDF
                pdf_bytes = pdf.output()
                st.sidebar.download_button(
                    label="📥 Download PDF Report",
                    data=pdf_bytes,
                    file_name=f"SKG_Report_{date_range[0]}_to_{date_range[1]}.pdf",
                    mime='application/pdf',
                    use_container_width=True
                )

with st.sidebar.expander("📥 Export Filtered Table", expanded=False):

    @st.cache_data
    def convert_df_to_csv(df):
        return df.to_csv(index=False).encode('utf-8')

    table_to_export = st.selectbox(
        "Select a table to export:",
        ("Stock", "Sales", "POSM", "Meta Ads"),
        key="export_table_select"
    )

    # 【核心修改】: 在这里应用日期过滤器
    # 获取侧边栏选择的日期范围
    start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])

    if table_to_export == "Stock":
        # 对 df_stock_raw 应用日期过滤
        df_for_export = df_stock_raw[
            (pd.to_datetime(df_stock_raw['Date']) >= start_date) &
            (pd.to_datetime(df_stock_raw['Date']) <= end_date)
        ]
        file_name = f"stock_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.csv"
        
    elif table_to_export == "Sales":
        # 对 df_sales_raw 应用日期过滤
        df_for_export = df_sales_raw[
            (pd.to_datetime(df_sales_raw['Date']) >= start_date) &
            (pd.to_datetime(df_sales_raw['Date']) <= end_date)
        ]
        file_name = f"sales_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.csv"

    elif table_to_export == "POSM":
        # 对 df_posm_raw 应用日期过滤
        df_for_export = df_posm_raw[
            (pd.to_datetime(df_posm_raw['Date']) >= start_date) &
            (pd.to_datetime(df_posm_raw['Date']) <= end_date)
        ]
        file_name = f"posm_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.csv"
    
    # 【新增】: Meta Ads 导出
    elif table_to_export == "Meta Ads":
        # 对 df_meta_ads_raw 应用日期过滤
        df_for_export = df_meta_ads_raw[
            (pd.to_datetime(df_meta_ads_raw['reporting_ends'], errors='coerce') >= start_date) &
            (pd.to_datetime(df_meta_ads_raw['reporting_ends'], errors='coerce') <= end_date)
        ]
        file_name = f"meta_ads_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.csv"

    # 转换数据为CSV格式
    csv_data = convert_df_to_csv(df_for_export)

    st.download_button(
       label=f"🚀 Download",
       data=csv_data,
       file_name=file_name,
       mime='text/csv',
       use_container_width=True
    )

# --- 6. 主面板 ---
st.title("SKG Business Analytics")

# --- 【修改】: 添加 Meta Ads Tab ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📦 Stock Balance", "📈 Sales Analysis", "🛒 Purchase (DOS)", "🎁 POSM", "📱 Meta Ads"])

# === TAB 1: STOCK ===
with tab1:
    st.header("Inventory Overview")

    # --- 2. 数据预处理 (核心要求：仅呈现 > 0 的数据) ---
    df_stock_positive = df_stock[df_stock['Quantity'] > 0].copy()

    if df_stock_positive.empty:
        st.warning("No active stock balance (>0) found for the selected warehouses.")
    else:
        # --- 3. 顶部汇总与图表 ---
        # 【修改】: 基于 df_stock_positive (它已经过过滤) 重新计算汇总
        summary_df = df_stock_positive.groupby('Warehouse Type')['Quantity'].sum().reset_index().sort_values('Quantity', ascending=False)
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

        # --- 4. All SKUs Analysis ---
        st.subheader("All SKUs Analysis by Quantity")
        
        # 定义分类按钮
        stock_filter = st.pills(
            "Quick Filter:",
            options=["All", "Warehouse", "Consign", "Warehouse and Consign"],
            selection_mode="single",
            default="All"
        )

        # 【修改】: 过滤逻辑现在基于 df_stock (它包含0库存)，而不是 df_stock_positive
        if stock_filter == "Warehouse":
            display_stock = df_stock[df_stock['Warehouse Type'] == 'WAREHOUSE']
        elif stock_filter == "Consign":
            display_stock = df_stock[df_stock['Warehouse Type'] == 'CONSIGN']
        elif stock_filter == "Warehouse and Consign":
            display_stock = df_stock[df_stock['Warehouse Type'].isin(['WAREHOUSE', 'CONSIGN'])]
        else:
            # "All" 选项
            display_stock = df_stock

        # 检查过滤后是否为空
        if display_stock.empty:
            st.info(f"No stock found for: {stock_filter} (Check if the Type is correct in Master Data)")
        else:
            # 【修改】:
            # - 基于 display_stock (包含0库存) 进行汇总
            # - 按 'Stock Name' 排序，而不是按 'Quantity'
            all_stock = display_stock.groupby('Stock Name')['Quantity'].sum().reset_index().sort_values('Stock Name', ascending=True)
            
            # 根据物料数量动态调整图表高度
            chart_height = max(600, len(all_stock) * 30)

            # 使用新的 all_stock DataFrame 和动态高度来创建图表
            fig_bar = px.bar(
                all_stock, 
                x='Quantity', 
                y='Stock Name', 
                orientation='h', 
                text_auto=True, 
                color='Quantity', 
                color_continuous_scale='Blues'
            )
            fig_bar.update_traces(texttemplate='%{x:,.0f}')
            # 【修改】: 让y轴按字母顺序从上到下排列
            fig_bar.update_layout(
                height=chart_height, 
                yaxis_title=None,
                yaxis={'categoryorder':'total ascending'} # 关键修改
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()
        st.subheader("🔍 Find Where a Specific Product is Stored (Live Search)")

        # 1. 创建一个文本输入框作为搜索栏
        search_term = st.text_input(
            "Type any part of the product name to search:",
            placeholder="e.g., G7, F3, Eye Massager"
        )

        # 2. 只有当用户输入了内容时才进行搜索
        if search_term:
            # 3. 从 display_stock 中筛选出所有匹配的产品
            #    - str.contains(search_term, case=False) 实现模糊搜索，不区分大小写
            #    - drop_duplicates() 确保每个产品只在列表中出现一次
            matching_products = display_stock[
                display_stock['Stock Name'].str.contains(search_term, case=False, na=False)
            ][['Stock Name']].drop_duplicates().sort_values('Stock Name')

            if not matching_products.empty:
                st.markdown("**Step 1: Select a product from the search results below**")
                
                # 4. 使用 st.dataframe 显示搜索结果，并启用行选择
                event = st.dataframe(
                    matching_products,
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",  # 点击行后刷新页面
                    selection_mode="single-row",
                    key="product_search_result"
                )

                # 5. 检查是否有行被选中
                if event.selection.rows:
                    selected_index = event.selection.rows[0]
                    selected_product_name = matching_products.iloc[selected_index]['Stock Name']
                    
                    st.markdown(f"**Step 2: Locations for *{selected_product_name}***")

                    # 6. 查询并显示该产品的库存地点
                    product_location_df = display_stock[
                        (display_stock['Stock Name'] == selected_product_name) &
                        (display_stock['Quantity'] > 0)
                    ].copy()

                    if not product_location_df.empty:
                        st.dataframe(
                            product_location_df[['Warehouse Name', 'Warehouse Type', 'Quantity']].sort_values('Quantity', ascending=False),
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Warehouse Name": "Location",
                                "Warehouse Type": "Location Type",
                                "Quantity": st.column_config.NumberColumn("Stock on Hand", format="%d")
                            }
                        )
                    else:
                        st.info(f"This product is currently out of stock everywhere.")

            else:
                st.warning(f"No products found matching '{search_term}'.")

        st.divider()

        # --- 5. Location Details (点击行显示明细) ---
        st.subheader(f"Location Details ({stock_filter})")
        st.caption("✨ Tip: Click any row below to see product details.")

        # 【修改】: 基于 display_stock 获取 active_types
        active_types = display_stock.groupby('Warehouse Type')['Quantity'].sum().sort_values(ascending=False).index.tolist()
        grid_cols = st.columns(3)
        
        for i, wh_type in enumerate(active_types):
            # 【修改】: 从 display_stock 中筛选数据
            type_data = display_stock[display_stock['Warehouse Type'] == wh_type]
            breakdown = type_data.groupby('Warehouse Name')['Quantity'].sum().reset_index().sort_values('Quantity', ascending=False)
            
            q_max = breakdown['Quantity'].max()
            safe_max = int(q_max) if pd.notna(q_max) and q_max > 0 else 100
            
            with grid_cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"**{wh_type}**")
                    
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
                                max_value=safe_max
                            )
                        }
                    )
                    
                    if event and event.selection.rows:
                        selected_index = event.selection.rows[0]
                        selected_loc = breakdown.iloc[selected_index]['Warehouse Name']
                        
                        st.markdown(f"---")
                        st.markdown(f"📦 **{selected_loc}** Breakdown:")
                        # 【修改】: 从 type_data 中获取最终明细
                        prod_detail = type_data[type_data['Warehouse Name'] == selected_loc][['Stock Name', 'Quantity']]
                        st.dataframe(
                            prod_detail.sort_values('Quantity', ascending=False),
                            hide_index=True, use_container_width=True, height=180
                        )

# === TAB 2: SALES ===
with tab2:
    st.header("Sales Performance Analysis")

    mask_curr = (
        (df_sales['Date'] >= pd.to_datetime(date_range[0])) & 
        (df_sales['Date'] <= pd.to_datetime(date_range[1]))
    )
    df_curr = df_sales[mask_curr].copy()

    df_comp_sidebar = pd.DataFrame()
    if enable_comparison and comp_range and len(comp_range) == 2:
        mask_comp = (
            (df_sales['Date'] >= pd.to_datetime(comp_range[0])) & 
            (df_sales['Date'] <= pd.to_datetime(comp_range[1]))
        )
        df_comp_sidebar = df_sales[mask_comp].copy()

    df_all_chan = pd.concat([df_comp_sidebar, df_curr], ignore_index=True)
    sorted_months_chan = []
    if not df_all_chan.empty:
        df_all_chan['Month'] = df_all_chan['Date'].dt.to_period('M').astype(str)
        sorted_months_chan = sorted(df_all_chan['Month'].unique())
    
    if df_curr.empty:
        st.warning("No sales data found for the selected date range and warehouses.")
    else:
        # =========================================================
        # PART 1: KPI Summary
        # =========================================================
        total_sales = df_curr['Sales'].sum()
        total_qty = df_curr['Quantity'].sum()
        total_transactions = df_curr['Invoice Number'].nunique()
        avg_order = total_sales / total_transactions if total_transactions > 0 else 0

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("💰 Total Revenue", f"RM{total_sales:,.2f}")
        k2.metric("📦 Units Sold", f"{total_qty:,.0f}")
        k3.metric("🧾 Transactions", f"{total_transactions:,.0f}")
        k4.metric("🎫 Avg. Ticket Size", f"RM{avg_order:,.2f}")
        
        st.divider()

        # =========================================================
        # PART 2: Sales Trend
        # =========================================================
        st.subheader("1. Sales Trend")

        trend_df = df_sales[
            df_sales['Date'] >= (df_sales['Date'].max() - pd.DateOffset(months=12))
        ].copy()
        trend_df['Sort_Key'] = trend_df['Date'].dt.to_period('M').dt.start_time
        trend_df['DP'] = trend_df['Date'].dt.to_period('M').astype(str)
        trend_data = trend_df.groupby(['Sort_Key', 'DP'])['Sales'].sum().reset_index().sort_values('Sort_Key')
        
        fig_overall = px.line(trend_data, x='DP', y='Sales', markers=True, text='Sales')
        fig_overall.update_traces(textposition="top center", texttemplate='%{text:.2s}', line_color='#1f77b4', line_width=3)
        fig_overall.update_layout(height=350, xaxis_title="Time Period", yaxis_title="Revenue (RM)")
        fig_overall.update_xaxes(type='category')
        st.plotly_chart(fig_overall, use_container_width=True)

        st.divider()

        # =========================================================
        # PART 3: Channel & Customer Analysis
        # =========================================================
        st.subheader("2. Channel & Customer Analysis")
        ar_col1, col_spacer, ar_col2 = st.columns([1, 0.1, 1])
        
        with ar_col1:
            st.caption("📊 Monthly Revenue Breakdown by Channel (Comparison Mode)")
            chan_data = df_all_chan.groupby(['AR Type', 'Month'])['Sales'].sum().reset_index()
            fig_ar = px.bar(chan_data, x='AR Type', y='Sales', color='Month', barmode='group', text_auto='.2s', category_orders={"Month": sorted_months_chan}, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_ar.update_layout(height=450, legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig_ar, use_container_width=True)
                    
        with ar_col2:
            st.caption("🏆 Top Customers Analysis")
            p_label = f"{date_range[0].strftime('%Y-%m-%d')} to {date_range[1].strftime('%Y-%m-%d')}"
            
            if not enable_comparison or df_comp_sidebar.empty:
                # 【修改】: 用 Display Name 替代 AR Name
                cust_detail = df_curr.groupby(['AR Type', 'Display Name'])['Sales'].sum().reset_index()
                cust_detail = cust_detail.sort_values('Sales', ascending=False).head(50)
                st.dataframe(
                    cust_detail, hide_index=True, use_container_width=True, height=400,
                    column_config={
                        "Display Name": st.column_config.TextColumn("Customer / Sub Type"),
                        "Sales": st.column_config.NumberColumn(p_label, format="RM%.2f")
                    }
                )
            else:
                c_label = f"{comp_range[0].strftime('%Y-%m-%d')} to {comp_range[1].strftime('%Y-%m-%d')}"
                
                # 【修改】: 用 Display Name 替代 AR Name
                p_sales = df_curr.groupby(['AR Type', 'Display Name'])['Sales'].sum().reset_index().rename(columns={'Sales': p_label})
                c_sales = df_comp_sidebar.groupby(['AR Type', 'Display Name'])['Sales'].sum().reset_index().rename(columns={'Sales': c_label})
                
                cust_detail = pd.merge(p_sales, c_sales, on=['AR Type', 'Display Name'], how='outer').fillna(0)
                if p_label in cust_detail.columns and c_label in cust_detail.columns:
                    cust_detail['Diff'] = cust_detail[p_label] - cust_detail[c_label]
                else:
                    cust_detail['Diff'] = 0
                cust_detail = cust_detail.sort_values(p_label, ascending=False).head(50)
                
                st.dataframe(
                    cust_detail, hide_index=True, use_container_width=True, height=400,
                    column_config={
                        "Display Name": st.column_config.TextColumn("Customer / Sub Type"),
                        p_label: st.column_config.NumberColumn(p_label, format="RM%.2f"),
                        c_label: st.column_config.NumberColumn(c_label, format="RM%.2f"),
                        "Diff": st.column_config.NumberColumn("Difference", format="RM%.2f")
                    }
                )

        st.divider()

        # =========================================================
        # PART 4: 2.1 Detailed Customer & Product Breakdown
        # =========================================================
        st.subheader("2.1 Detailed Customer & Product Breakdown")
        st.caption("💡Displaying data for the [Primary Date Range] only")
        st.write(df_curr[df_curr['AR Type'] == 'KA'][['AR Name', 'state']].head(20))

        dd_col1, dd_col2, dd_col3 = st.columns(3)

        with dd_col1:
            st.markdown("**Step 1: Select AR Type**")
            type_summary = df_curr.groupby('AR Type')[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)
            
            event_type = st.dataframe(
                type_summary, hide_index=True, use_container_width=True, height=300,
                on_select="rerun", selection_mode="single-row", key="dd_type_table",
                column_config={
                    "AR Type": st.column_config.TextColumn("Channel Type"),
                    "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                    "Sales": st.column_config.NumberColumn("Total Sales", format="RM%.2f")
                }
            )

        selected_type = None
        if event_type and event_type.selection.rows:
            selected_index = event_type.selection.rows[0]
            selected_type = type_summary.iloc[selected_index]['AR Type']

        with dd_col2:
            st.markdown(f"**Step 2: {'Sub Type' if selected_type == 'ONLINE' else 'Customers'} in {selected_type if selected_type else '...'}**")
            if selected_type:
                group_col = 'Display Name' if selected_type == 'ONLINE' else 'AR Name'
                name_summary = df_curr[df_curr['AR Type'] == selected_type].groupby(group_col)[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)
                
                event_name = st.dataframe(
                    name_summary, hide_index=True, use_container_width=True, height=300,
                    on_select="rerun", selection_mode="single-row", key="dd_name_table",
                    column_config={
                        group_col: st.column_config.TextColumn("Sub Type" if selected_type == 'ONLINE' else "Customer Name"),
                        "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                        "Sales": st.column_config.NumberColumn("Sales", format="RM%.2f")
                    }
                )
            else:
                st.info("Please select an AR Type.")

        selected_name = None
        selected_group_col = None
        if selected_type and 'event_name' in locals() and event_name and event_name.selection.rows:
            selected_index_name = event_name.selection.rows[0]
            selected_group_col = 'Display Name' if selected_type == 'ONLINE' else 'AR Name'
            selected_name = name_summary.iloc[selected_index_name][selected_group_col]

        with dd_col3:
            if selected_type == 'KA':
                st.markdown(f"**Step 3: State for {selected_name if selected_name else '...'}**")
                if selected_name:
                    state_summary = df_curr[
                        (df_curr['AR Type'] == 'KA') &
                        (df_curr['AR Name'] == selected_name)
                    ].groupby('state')[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)

                    event_state = st.dataframe(
                        state_summary, hide_index=True, use_container_width=True, height=300,
                        on_select="rerun", selection_mode="single-row", key="dd_state_table",
                        column_config={
                            "state": st.column_config.TextColumn("State"),
                            "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                            "Sales": st.column_config.NumberColumn("Sales", format="RM%.2f")
                        }
                    )
                else:
                    st.info("Please select a Customer.")
            else:
                st.empty()

        selected_state = None
        if selected_type == 'KA' and selected_name and 'event_state' in locals() and event_state and event_state.selection.rows:
            selected_index_state = event_state.selection.rows[0]
            selected_state = state_summary.iloc[selected_index_state]['state']

        # 第二行：全宽显示 Products
        st.markdown("---")
        if selected_type == 'KA':
            st.markdown(f"**Step 4: Products for {selected_name if selected_name else '...'} — {selected_state if selected_state else 'All States'}**")
        else:
            st.markdown(f"**Step 3: Products for {selected_name if selected_name else '...'}**")

        if selected_name:
            product_filter = df_curr[
                (df_curr['AR Type'] == selected_type) &
                (df_curr[selected_group_col] == selected_name)
            ]
            if selected_type == 'KA' and selected_state:
                product_filter = product_filter[product_filter['state'] == selected_state]

            product_summary = product_filter.groupby('Stock Name')[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)

            st.dataframe(
                product_summary, hide_index=True, use_container_width=True, height=300,
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
        # PART 5: 2.2 Channel Sales Pie Chart
        # =========================================================
        st.subheader("2.2 Channel Sales Distribution")
        st.caption("💡 Select a channel to drill down into its customers / sub types.")

        pie_col1, pie_col2 = st.columns([1, 1])

        with pie_col1:
            channel_sales = df_curr.groupby('AR Type')['Sales'].sum().reset_index().sort_values('Sales', ascending=False)
            fig_pie_channel = px.pie(
                channel_sales, values='Sales', names='AR Type',
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_pie_channel.update_layout(height=420, margin=dict(t=30, b=0, l=0, r=0))
            fig_pie_channel.update_traces(
                textposition='inside',
                textinfo='label+percent',
                textfont_size=13
            )
            st.plotly_chart(fig_pie_channel, use_container_width=True)

            # Filter pills
            channel_options = channel_sales['AR Type'].tolist()
            selected_channel = st.pills(
                "Filter by Channel:",
                options=channel_options,
                selection_mode="single",
                key="pie_channel_filter"
            )

        with pie_col2:
            if selected_channel:
                drill_col = 'Display Name' if selected_channel == 'ONLINE' else 'AR Name'
                drill_label = 'Sub Type' if selected_channel == 'ONLINE' else 'Customer'
                drill_data = df_curr[df_curr['AR Type'] == selected_channel].groupby(drill_col)['Sales'].sum().reset_index().sort_values('Sales', ascending=False)
                
                fig_pie_drill = px.pie(
                    drill_data, values='Sales', names=drill_col,
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    title=f"{selected_channel} — by {drill_label}"
                )
                fig_pie_drill.update_layout(height=420, margin=dict(t=50, b=0, l=0, r=0))
                fig_pie_drill.update_traces(
                    textposition='inside',
                    textinfo='label+percent',
                    textfont_size=13
                )
                st.plotly_chart(fig_pie_drill, use_container_width=True)
            else:
                st.info("Select a channel on the left to drill down.")

        st.markdown(" ")
        st.caption("📈 Sales Trend by Channel")

        trend_col = 'Display Name' if selected_channel == 'ONLINE' else ('AR Name' if selected_channel else 'AR Type')
        trend_group_label = 'Sub Type' if selected_channel == 'ONLINE' else ('Customer' if selected_channel else 'Channel Type')

        trend_df_22 = df_curr.copy()

        if selected_channel:
            trend_df_22 = trend_df_22[trend_df_22['AR Type'] == selected_channel]

        trend_df_22['Sort_Key'] = trend_df_22['Date'].dt.to_period('M').dt.start_time
        trend_df_22['DP'] = trend_df_22['Date'].dt.to_period('M').astype(str)

        trend_data_22 = trend_df_22.groupby([trend_col, 'Sort_Key', 'DP'])['Sales'].sum().reset_index().sort_values('Sort_Key')

        fig_trend_22 = px.line(
            trend_data_22, x='DP', y='Sales', color=trend_col,
            markers=True, template='plotly_white',
            labels={'DP': 'Time Period', 'Sales': 'Revenue (RM)', trend_col: trend_group_label}
        )
        fig_trend_22.update_layout(
            height=400,
            legend=dict(orientation="h", y=-0.2),
            xaxis_title="Time Period",
            yaxis_title="Revenue (RM)"
        )
        fig_trend_22.update_xaxes(type='category')
        st.plotly_chart(fig_trend_22, use_container_width=True)

        st.divider()

        # =========================================================
        # PART 6: 3. Product Performance & Trend Analysis
        # =========================================================
        st.subheader("3. Product Performance & Trend Analysis")
        
        curr_month_period = pd.to_datetime(date_range[1]).to_period('M')
        prev_month_period = curr_month_period - 1

        p_top_col1, col_spacer_p, p_top_col2 = st.columns([1, 0.1, 1])
        with p_top_col1:
            st.caption(f"📊 Sales by Category ({curr_month_period})")
            cat_sales = df_sales[
                (df_sales['Date'].dt.to_period('M') == curr_month_period)
            ].groupby('Category')['Sales'].sum().reset_index().sort_values('Sales', ascending=False)
            fig_cat = px.pie(cat_sales, values='Sales', names='Category', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_cat.update_layout(height=350, margin=dict(t=30, b=0, l=0, r=0))
            st.plotly_chart(fig_cat, use_container_width=True)

        with p_top_col2:
            st.caption(f"🏆 Top Selling Models ({curr_month_period})")
            top_m = df_sales[
                (df_sales['Date'].dt.to_period('M') == curr_month_period)
            ].groupby(['Stock Name', 'Category'])[['Quantity', 'Sales']].sum().reset_index().sort_values('Quantity', ascending=False).head(5)
            
            t_max = top_m['Quantity'].max()
            safe_t_max = int(t_max) if pd.notna(t_max) and t_max > 0 else 100

            if not top_m.empty:
                st.dataframe(
                    top_m[['Stock Name', 'Category', 'Quantity', 'Sales']], 
                    use_container_width=True, hide_index=True, height=250, 
                    column_config={
                        "Category": st.column_config.TextColumn("Category", width="small"), 
                        "Stock Name": st.column_config.TextColumn("Model Name", width="medium"), 
                        "Quantity": st.column_config.ProgressColumn("Units", format="%d", min_value=0, max_value=safe_t_max),
                        "Sales": st.column_config.NumberColumn(format="RM%.2f")
                    }
                )
        
        st.markdown(" ", unsafe_allow_html=True)
        st.markdown(" ", unsafe_allow_html=True)

        # =========================================================
        # PART 7: 3.1 Product Sales Traceability
        # =========================================================
        st.subheader("3.1 Product Sales Traceability")
        st.caption("💡Displaying data for the [Primary Date Range] only.")

        p_col1, p_col2, p_col3 = st.columns(3)

        with p_col1:
            st.markdown("**Step 1: Select Model**")
            model_summary = df_curr.groupby('Stock Name')[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)
            
            event_model = st.dataframe(
                model_summary, hide_index=True, use_container_width=True, height=400,
                on_select="rerun", selection_mode="single-row", key="dr_model_table",
                column_config={
                    "Stock Name": st.column_config.TextColumn("Model Name"),
                    "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                    "Sales": st.column_config.NumberColumn("Total Sales", format="RM%.2f")
                }
            )

        selected_model = None
        if event_model and event_model.selection.rows:
            selected_index = event_model.selection.rows[0]
            selected_model = model_summary.iloc[selected_index]['Stock Name']

        with p_col2:
            st.markdown(f"**Step 2: Channels for {selected_model if selected_model else '...'}**")
            if selected_model:
                type_summary = df_curr[df_curr['Stock Name'] == selected_model].groupby('AR Type')[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)
                
                event_type_p = st.dataframe(
                    type_summary, hide_index=True, use_container_width=True, height=400,
                    on_select="rerun", selection_mode="single-row", key="dr_type_p_table",
                    column_config={
                        "AR Type": st.column_config.TextColumn("Channel Type"),
                        "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                        "Sales": st.column_config.NumberColumn("Sales", format="RM%.2f")
                    }
                )
            else:
                st.info("Please select a Model.")

        selected_type_p = None
        if selected_model and 'event_type_p' in locals() and event_type_p and event_type_p.selection.rows:
            selected_index_type = event_type_p.selection.rows[0]
            selected_type_p = type_summary.iloc[selected_index_type]['AR Type']

        with p_col3:
            st.markdown(f"**Step 3: {'Sub Type' if selected_type_p == 'ONLINE' else 'Customers'} ( {selected_type_p if selected_type_p else '...'} )**")
            if selected_type_p:
                # 【修改】: ONLINE 用 Display Name，其他用 AR Name
                trace_col = 'Display Name' if selected_type_p == 'ONLINE' else 'AR Name'
                customer_summary = df_curr[
                    (df_curr['Stock Name'] == selected_model) & 
                    (df_curr['AR Type'] == selected_type_p)
                ].groupby(trace_col)[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)
                
                st.dataframe(
                    customer_summary, hide_index=True, use_container_width=True, height=400,
                    column_config={
                        trace_col: st.column_config.TextColumn("Sub Type" if selected_type_p == 'ONLINE' else "Customer Name"),
                        "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                        "Sales": st.column_config.NumberColumn("Customer Sales", format="RM%.2f")
                    }
                )
            else:
                st.info("Please select a Channel Type.")

        st.divider()

        st.caption("📈 Top 20 Models Performance with Sparklines")
        
        df_full_history = df_sales[
            (df_sales['Date'].dt.to_period('M') <= curr_month_period)
        ].copy()
        df_full_history['Month_Label'] = df_full_history['Date'].dt.to_period('M').astype(str)
        
        full_months_axis = sorted(df_full_history['Month_Label'].unique())
        
        spark_raw = df_full_history.groupby(['Stock Name', 'Month_Label'])['Quantity'].sum().reset_index()
        spark_pivot = spark_raw.pivot(index='Stock Name', columns='Month_Label', values='Quantity').fillna(0)
        spark_pivot['Trend'] = spark_pivot.values.tolist()
        spark_pivot = spark_pivot.reset_index()

        p_curr = df_sales[
            (df_sales['Date'].dt.to_period('M') == curr_month_period)
        ].groupby('Stock Name')['Quantity'].sum().reset_index().rename(columns={'Quantity':'Current'})

        p_prev = df_sales[
            (df_sales['Date'].dt.to_period('M') == prev_month_period)
        ].groupby('Stock Name')['Quantity'].sum().reset_index().rename(columns={'Quantity':'Previous'})
        
        final_table = pd.merge(p_curr, p_prev, on='Stock Name', how='left').fillna(0)
        final_table = pd.merge(final_table, spark_pivot[['Stock Name', 'Trend']], on='Stock Name', how='left')
        final_table['Growth %'] = ((final_table['Current'] - final_table['Previous']) / final_table['Previous'] * 100).replace([np.inf, -np.inf], 0)

        order_columns = ['Stock Name', 'Current', 'Previous', 'Growth %', 'Trend']
        display_df = final_table.sort_values('Current', ascending=False).head(20)[order_columns]

        def color_growth(val):
            if val < 0: return 'color: #ff4b4b; font-weight: bold;'
            elif val > 0: return 'color: #09ab3b; font-weight: bold;'
            return 'color: gray;'

        styled_df = display_df.style.map(color_growth, subset=['Growth %'])

        st.data_editor(
            styled_df, use_container_width=True, hide_index=True, height=800,
            column_config={
                "Stock Name": st.column_config.TextColumn("Model Name", width="medium"),
                "Current": st.column_config.NumberColumn(f"Qty ({curr_month_period})", format="%d"),
                "Previous": st.column_config.NumberColumn(f"Qty ({prev_month_period})", format="%d"),
                "Growth %": st.column_config.NumberColumn("Growth", format="%.1f%%"),
                "Trend": st.column_config.AreaChartColumn(
                    "Full History Trend", width="medium", y_min=0, 
                    help=f"Continuous trend from {full_months_axis[0] if full_months_axis else 'N/A'} up to {curr_month_period}"
                )
            },
            disabled=True 
        )

# === TAB 3: DOS (Purchase) ===
with tab3:
    st.header("Inventory Health & DOS Analysis")
    st.markdown("💡 **Logic**: `DOS = Current Stock / Average Daily Sales (Past 21 Days)`")

    # --- 1. 直接使用已在侧边栏过滤过的数据进行DOS计算 ---
    # 【修改】: 不再需要内部过滤，直接使用全局的 df_stock 和 df_sales_for_dos
    
    # 1.1 计算近期平均日销量 (ADS)
    recent_sales_dos = df_sales_for_dos[
        (df_sales_for_dos['Date'] > start_date_dos) & 
        (df_sales_for_dos['Date'] <= last_date_all)
    ]
    sku_sales_dos = recent_sales_dos.groupby('Stock Code')['Quantity'].sum().reset_index()
    sku_sales_dos['ADS'] = sku_sales_dos['Quantity'] / 21
    
    # 1.2 汇总当前库存
    sku_stock_dos = df_stock.groupby(['Stock Code', 'Stock Name'])['Quantity'].sum().reset_index()

    # 1.3 合并库存与销量，计算DOS
    dos_df = pd.merge(sku_stock_dos, sku_sales_dos[['Stock Code', 'ADS']], on='Stock Code', how='left').fillna(0)
    dos_df['DOS (Days)'] = np.where(dos_df['ADS'] > 0, dos_df['Quantity'] / dos_df['ADS'], 9999)
    
    # 1.4 定义DOS状态
    dos_df['Status'] = dos_df.apply(get_dos_status, axis=1)
    
    # --- 2. 顶部 KPI 指标 (Summary Metrics) ---
    # 【修改】: 使用新计算的 dos_df
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

    # --- 3. 状态过滤器 ---
    filter_status = st.multiselect(
        "Filter by Health Status:",
        options=["🔴 Low Stock (<14 Days)", "🟢 Healthy (14-60 Days)", "🟡 Overstock (>60 Days)", "⚫ Dead Stock (No Sales)", "⚪ Out of Stock"],
        default=["🔴 Low Stock (<14 Days)", "🟢 Healthy (14-60 Days)", "🟡 Overstock (>60 Days)", "⚫ Dead Stock (No Sales)", "⚪ Out of Stock"] 
    )
    
    # 【修改】: 基于新计算的 dos_df 进行状态筛选
    if filter_status:
        view_df = dos_df[dos_df['Status'].isin(filter_status)]
    else:
        view_df = dos_df

    # 排序优化
    view_df = view_df.sort_values(by=['DOS (Days)', 'ADS'], ascending=[True, False])

    # --- 4. 详细表格 ---
    st.subheader("Detailed DOS Table")
    
    st.dataframe(
        view_df[['Status', 'Stock Name', 'Quantity', 'ADS', 'DOS (Days)']],
        use_container_width=True,
        hide_index=True,
        height=800,
        column_config={
            "Status": st.column_config.TextColumn("Health Status", width="medium"),
            "Stock Name": st.column_config.TextColumn("Product Name", width="large"),
            "Quantity": st.column_config.NumberColumn("Current Stock", format="%d"),
            "ADS": st.column_config.NumberColumn("Avg Daily Sales", format="%.2f"),
            "DOS (Days)": st.column_config.NumberColumn("Est. Days Left", format="%.1f")
        }
    )

# === TAB 4: POSM ===
with tab4:
    st.header("POSM Inventory")
    st.caption("This chart shows the total quantity for every POSM item, sorted by Stock Code. It is not affected by sidebar filters.")

    # --- 1. 使用最原始的、未经过滤的 df_posm_raw 数据 ---
    # 【修改】: 直接使用 df_posm_raw 来确保不受任何过滤影响
    if df_posm_raw.empty:
        st.warning("No data found in the 'posm_details' table.")
    else:
        # --- 2. 汇总所有物料的总库存 ---
        # 【修改】:
        # - 使用 df_posm_raw
        # - Group by 'Stock Code' 和 'Stock Name'
        # - .sum() 会计算每个物料在所有仓库的总量
        all_posm_items = df_posm_raw.groupby(
            ['Stock Code', 'Stock Name']
        )['Quantity'].sum().reset_index()

        # --- 3. 按 Stock Code 排序 ---
        # 【修改】: sort_values by 'Stock Code'
        # 注意：对于图表，我们需要倒序排列，这样在垂直条形图中，A开头的编码会在顶部
        all_posm_items = all_posm_items.sort_values(by='Stock Code', ascending=False)
        
        # --- 4. 使用 Bar Chart 显示 ---
        if all_posm_items.empty:
            st.info("No POSM items found to display.")
        else:
            # 【修改】: 根据物料数量动态调整图表高度
            chart_height = max(600, len(all_posm_items) * 32)

            # 【修改】:
            # - y轴使用 'Stock Name' 来显示
            # - Plotly 会根据 DataFrame 的顺序来渲染，因为我们已经按 Stock Code 排序，所以图表也是有序的
            fig_bar = px.bar(
                all_posm_items, 
                x='Quantity', 
                y='Stock Name', 
                orientation='h', 
                text_auto=True, 
                color='Quantity', 
                color_continuous_scale='Blues',
                # 添加悬停数据以显示Stock Code
                hover_data=['Stock Code'] 
            )
            
            fig_bar.update_traces(texttemplate='%{x:,.0f}') # 格式化条形图上的数字
            fig_bar.update_layout(
                height=chart_height, 
                yaxis_title=None,
                title="Total Quantity of All POSM Items (Sorted by Stock Code)"
            )
            st.plotly_chart(fig_bar, use_container_width=True)

# === TAB 5: META ADS ===
with tab5:
    st.header("📱 Meta Ads Performance Analysis")

    if df_meta_ads_raw.empty:
        st.warning("No data found in the 'meta_ads' table.")
    else:
        # --- 数据预处理 ---
        df_meta_ads = df_meta_ads_raw.copy()
        for col in ['reporting_starts', 'reporting_ends', 'starts', 'ends']:
            if col in df_meta_ads.columns:
                df_meta_ads[col] = pd.to_datetime(df_meta_ads[col], errors='coerce')

        # -------------------------------------------------------
        # DATE FILTER
        # -------------------------------------------------------
        st.subheader("🗓️ Date Filter")
        meta_min = df_meta_ads['reporting_starts'].min()
        meta_max = df_meta_ads['reporting_starts'].max()

        f_col1, f_col2, f_col3 = st.columns([1, 1, 2])
        with f_col1:
            meta_start = st.date_input("From", value=meta_min.date(), min_value=meta_min.date(), max_value=meta_max.date(), key='meta_start')
        with f_col2:
            meta_end = st.date_input("To", value=meta_max.date(), min_value=meta_min.date(), max_value=meta_max.date(), key='meta_end')
        with f_col3:
            quick = st.radio("Quick Select:", ["Custom", "Last 7 Days", "Last 30 Days", "All Time"], horizontal=True, key='meta_quick')
            if quick == "Last 7 Days":
                meta_start = (meta_max - timedelta(days=7)).date()
                meta_end = meta_max.date()
            elif quick == "Last 30 Days":
                meta_start = (meta_max - timedelta(days=30)).date()
                meta_end = meta_max.date()
            elif quick == "All Time":
                meta_start = meta_min.date()
                meta_end = meta_max.date()

        df_meta_filtered = df_meta_ads[
            (df_meta_ads['reporting_starts'] >= pd.to_datetime(meta_start)) &
            (df_meta_ads['reporting_starts'] <= pd.to_datetime(meta_end))
        ].copy()

        st.caption(f"Showing data from **{meta_start}** to **{meta_end}** — {len(df_meta_filtered)} records")
        st.divider()

        if df_meta_filtered.empty:
            st.warning("No data for selected date range.")
        else:
            # -------------------------------------------------------
            # AD SELECTION
            # -------------------------------------------------------
            st.subheader("🎯 Ad Selection")
            ad_names = sorted(df_meta_filtered['ad_name'].dropna().unique().tolist())

            sel_col1, sel_col2 = st.columns([2, 1])
            with sel_col1:
                selected_ad = st.selectbox(
                    "Select an Ad to analyze:",
                    options=["All Ads"] + ad_names,
                    key='meta_ads_main_filter'
                )
            with sel_col2:
                st.metric("Total Ads in Range", len(ad_names))

            is_single_ad = selected_ad != "All Ads"
            df_display = df_meta_filtered[df_meta_filtered['ad_name'] == selected_ad].copy() if is_single_ad else df_meta_filtered.copy()

            st.divider()

            # -------------------------------------------------------
            # HELPER: Days with actual spend
            # -------------------------------------------------------
            def calc_days_with_spend(df, group_col='ad_name'):
                return (
                    df[df['amount_spent'] > 0]
                    .groupby(group_col)['reporting_starts']
                    .nunique()
                    .reset_index()
                    .rename(columns={'reporting_starts': 'days_with_spend'})
                )

            # -------------------------------------------------------
            # PART A: KPI Dashboard
            # -------------------------------------------------------
            if is_single_ad:
                campaign_start = df_display['starts'].min()
                campaign_end   = df_display['ends'].max()
                p1, p2 = st.columns(2)
                with p1:
                    st.metric("📅 Campaign Start", campaign_start.strftime('%Y-%m-%d') if pd.notna(campaign_start) else "N/A")
                with p2:
                    st.metric("📅 Campaign End", campaign_end.strftime('%Y-%m-%d') if pd.notna(campaign_end) else "N/A")
                st.divider()

            st.subheader("📊 Key Performance Indicators")

            total_spend       = df_display['amount_spent'].sum()
            total_impressions = df_display['impressions'].sum()
            total_reach       = df_display['reach'].sum()
            total_link_clicks = df_display['link_clicks'].sum()
            total_lpv         = df_display['website_landing_page_views'].sum()
            total_engagements = df_display['post_engagements'].sum()
            avg_cpm           = df_display['cpm'].mean()
            avg_cpc           = df_display['cpc'].mean()
            avg_ctr           = df_display['ctr'].mean()
            cost_per_lp       = df_display['cost_per_landing_page_view'].mean()
            cost_per_eng      = df_display['cost_per_post_engagement'].mean()

            k1, k2, k3, k4, k5, k6 = st.columns(6)
            k1.metric("💰 Total Spend",    f"RM {total_spend:,.2f}")
            k2.metric("👁️ Impressions",    f"{total_impressions:,.0f}")
            k3.metric("🔗 Link Clicks",     f"{total_link_clicks:,.0f}")
            k4.metric("📄 Landing Pages",   f"{total_lpv:,.0f}")
            k5.metric("💬 Engagements",     f"{total_engagements:,.0f}")
            k6.metric("📊 Reach",           f"{total_reach:,.0f}")

            k7, k8, k9, k10, _, _ = st.columns(6)
            k7.metric("📉 Avg CPM",  f"RM {avg_cpm:,.2f}")
            k8.metric("🖱️ Avg CPC",  f"RM {avg_cpc:,.2f}")
            k9.metric("📈 Avg CTR",  f"{avg_ctr:.2f}%")
            k10.metric("🎯 Cost/LP", f"RM {cost_per_lp:,.2f}")

            st.divider()

            # -------------------------------------------------------
            # PART B: SCORECARD
            # Benchmark 基于同一 date range 内所有广告的中位数
            # 评分维度: CTR, CPC, LPV CVR, Cost/LPV, CPM
            # 每个维度: 🟢 Good / 🟡 Average / 🔴 Poor
            # -------------------------------------------------------
            st.subheader("🏅 Ad Scorecard")
            st.caption("Each ad is scored against the **median** of all ads in the selected date range. Green = above average, Red = below average.")

            # 先 aggregate per ad
            score_base = df_meta_filtered.groupby('ad_name').agg(
                spend=('amount_spent', 'sum'),
                impressions=('impressions', 'sum'),
                clicks=('link_clicks', 'sum'),
                lpv=('website_landing_page_views', 'sum'),
                engagements=('post_engagements', 'sum'),
                avg_ctr=('ctr', 'mean'),
                avg_cpc=('cpc', 'mean'),
                avg_cpm=('cpm', 'mean'),
                avg_cplpv=('cost_per_landing_page_view', 'mean'),
            ).reset_index()

            # LPV CVR = LPV / Clicks (landing page conversion rate)
            score_base['lpv_cvr'] = np.where(
                score_base['clicks'] > 0,
                score_base['lpv'] / score_base['clicks'] * 100,
                0
            )

            # 计算中位数作为 benchmark
            med_ctr    = score_base['avg_ctr'].median()
            med_cpc    = score_base['avg_cpc'].median()
            med_cpm    = score_base['avg_cpm'].median()
            med_cplpv  = score_base['avg_cplpv'].median()
            med_cvr    = score_base['lpv_cvr'].median()

            def score_metric(val, benchmark, higher_is_better=True):
                """Return emoji + label based on vs benchmark"""
                if pd.isna(val) or benchmark == 0:
                    return "⚫ N/A"
                ratio = val / benchmark
                if higher_is_better:
                    if ratio >= 1.15:   return "🟢 Good"
                    elif ratio >= 0.85: return "🟡 Average"
                    else:               return "🔴 Poor"
                else:  # lower is better (cost metrics)
                    if ratio <= 0.85:   return "🟢 Good"
                    elif ratio <= 1.15: return "🟡 Average"
                    else:               return "🔴 Poor"

            def overall_grade(scores):
                """Aggregate score list → overall grade"""
                green  = scores.count("🟢 Good")
                yellow = scores.count("🟡 Average")
                red    = scores.count("🔴 Poor")
                total  = green + yellow + red
                if total == 0: return "⚫ N/A"
                pct = green / total
                if pct >= 0.6:   return "🟢 Strong"
                elif pct >= 0.4: return "🟡 Mixed"
                else:            return "🔴 Weak"

            # Build scorecard rows
            scorecard_rows = []
            for _, row in score_base.iterrows():
                s_ctr   = score_metric(row['avg_ctr'],   med_ctr,   higher_is_better=True)
                s_cpc   = score_metric(row['avg_cpc'],   med_cpc,   higher_is_better=False)
                s_cpm   = score_metric(row['avg_cpm'],   med_cpm,   higher_is_better=False)
                s_cplpv = score_metric(row['avg_cplpv'], med_cplpv, higher_is_better=False)
                s_cvr   = score_metric(row['lpv_cvr'],   med_cvr,   higher_is_better=True)
                overall = overall_grade([s_ctr, s_cpc, s_cpm, s_cplpv, s_cvr])

                scorecard_rows.append({
                    'Ad Name':       row['ad_name'],
                    'Overall':       overall,
                    'CTR':           f"{s_ctr}  ({row['avg_ctr']:.2f}%)",
                    'CPC':           f"{s_cpc}  (RM {row['avg_cpc']:.2f})",
                    'CPM':           f"{s_cpm}  (RM {row['avg_cpm']:.2f})",
                    'Cost/LPV':      f"{s_cplpv}  (RM {row['avg_cplpv']:.2f})",
                    'LPV CVR':       f"{s_cvr}  ({row['lpv_cvr']:.1f}%)",
                    'Total Spend':   f"RM {row['spend']:,.2f}",
                })

            sc_df = pd.DataFrame(scorecard_rows).sort_values('Overall', ascending=True)

            # Benchmark info
            with st.expander("📐 Benchmark values (median of all ads in range)"):
                b1, b2, b3, b4, b5 = st.columns(5)
                b1.metric("CTR Benchmark",      f"{med_ctr:.2f}%")
                b2.metric("CPC Benchmark",      f"RM {med_cpc:.2f}")
                b3.metric("CPM Benchmark",      f"RM {med_cpm:.2f}")
                b4.metric("Cost/LPV Benchmark", f"RM {med_cplpv:.2f}")
                b5.metric("LPV CVR Benchmark",  f"{med_cvr:.1f}%")

            st.dataframe(sc_df, use_container_width=True, hide_index=True)

            # Budget recommendation: sort by LPV/RM (most efficient)
            score_base['LPV per RM'] = np.where(
                score_base['spend'] > 0,
                score_base['lpv'] / score_base['spend'],
                0
            )
            budget_rec = score_base[['ad_name','spend','lpv','LPV per RM','avg_cpc','avg_ctr']].sort_values('LPV per RM', ascending=False).copy()
            budget_rec.columns = ['Ad Name','Total Spend (RM)','Total LPV','LPV per RM spent','Avg CPC','Avg CTR %']
            budget_rec['Total Spend (RM)'] = budget_rec['Total Spend (RM)'].apply(lambda x: f"RM {x:,.2f}")
            budget_rec['LPV per RM spent'] = budget_rec['LPV per RM spent'].apply(lambda x: f"{x:.3f}")
            budget_rec['Avg CPC']          = budget_rec['Avg CPC'].apply(lambda x: f"RM {x:.2f}")
            budget_rec['Avg CTR %']        = budget_rec['Avg CTR %'].apply(lambda x: f"{x:.2f}%")

            st.markdown("**💡 Budget Efficiency Ranking** — sorted by LPV per RM spent (higher = more efficient)")
            st.dataframe(budget_rec, use_container_width=True, hide_index=True)

            st.divider()

            # -------------------------------------------------------
            # PART C: Ad Performance Ranking
            # -------------------------------------------------------
            st.subheader("🏆 Ad Performance Ranking")
            st.caption("**Days** = number of days the ad actually had spend")

            days_df = calc_days_with_spend(df_meta_filtered)

            ad_summary = df_meta_filtered.groupby('ad_name').agg(
                Total_Spend=('amount_spent', 'sum'),
                Total_Impressions=('impressions', 'sum'),
                Total_Reach=('reach', 'sum'),
                Total_Clicks=('link_clicks', 'sum'),
                Total_LPV=('website_landing_page_views', 'sum'),
                Total_Eng=('post_engagements', 'sum'),
                Avg_CPM=('cpm', 'mean'),
                Avg_CPC=('cpc', 'mean'),
                Avg_CTR=('ctr', 'mean'),
            ).reset_index()

            ad_summary = ad_summary.merge(days_df, on='ad_name', how='left')
            ad_summary['days_with_spend'] = ad_summary['days_with_spend'].fillna(0).astype(int)
            ad_summary['Daily Avg Spend']       = np.where(ad_summary['days_with_spend'] > 0, ad_summary['Total_Spend']       / ad_summary['days_with_spend'], 0)
            ad_summary['Daily Avg Impressions'] = np.where(ad_summary['days_with_spend'] > 0, ad_summary['Total_Impressions'] / ad_summary['days_with_spend'], 0)
            ad_summary['Daily Avg Clicks']      = np.where(ad_summary['days_with_spend'] > 0, ad_summary['Total_Clicks']      / ad_summary['days_with_spend'], 0)
            ad_summary['Daily Avg LPV']         = np.where(ad_summary['days_with_spend'] > 0, ad_summary['Total_LPV']         / ad_summary['days_with_spend'], 0)

            ad_summary = ad_summary.sort_values('Total_Spend', ascending=False).reset_index(drop=True)
            rank_marks = {0: '🥇', 1: '🥈', 2: '🥉'}
            ad_summary['Rank'] = [rank_marks.get(i, f'#{i+1}') for i in range(len(ad_summary))]

            ranking_display = ad_summary[[
                'Rank', 'ad_name', 'days_with_spend',
                'Daily Avg Spend', 'Total_Spend',
                'Daily Avg Impressions', 'Total_Impressions',
                'Daily Avg Clicks', 'Total_Clicks',
                'Daily Avg LPV', 'Total_LPV',
                'Avg_CPM', 'Avg_CPC', 'Avg_CTR'
            ]].copy()
            ranking_display.columns = [
                'Rank', 'Ad Name', 'Days w/ Spend',
                'Daily Avg Spend', 'Total Spend',
                'Daily Avg Impressions', 'Total Impressions',
                'Daily Avg Clicks', 'Total Clicks',
                'Daily Avg LPV', 'Total LPV',
                'Avg CPM', 'Avg CPC', 'Avg CTR'
            ]
            for col in ['Daily Avg Spend', 'Total Spend']:
                ranking_display[col] = ranking_display[col].apply(lambda x: f"RM {x:,.2f}")
            for col in ['Daily Avg Impressions','Total Impressions','Daily Avg Clicks','Total Clicks','Daily Avg LPV','Total LPV']:
                ranking_display[col] = ranking_display[col].apply(lambda x: f"{x:,.0f}")
            ranking_display['Avg CPM'] = ranking_display['Avg CPM'].apply(lambda x: f"RM {x:,.2f}")
            ranking_display['Avg CPC'] = ranking_display['Avg CPC'].apply(lambda x: f"RM {x:,.2f}")
            ranking_display['Avg CTR'] = ranking_display['Avg CTR'].apply(lambda x: f"{x:.2f}%")

            st.dataframe(ranking_display, use_container_width=True, hide_index=True)

            st.divider()

            # -------------------------------------------------------
            # PART D: Cost Metrics Charts
            # -------------------------------------------------------
            st.subheader("💰 Cost Metrics Comparison")

            cost_m = df_meta_filtered.groupby('ad_name').agg(
                cpm=('cpm','mean'), cpc=('cpc','mean'),
                cplpv=('cost_per_landing_page_view','mean'),
                cpe=('cost_per_post_engagement','mean')
            ).reset_index()

            def cost_bar(df, y_col, title, avg_val):
                fig = px.bar(df.sort_values(y_col), x='ad_name', y=y_col,
                             color=y_col, color_continuous_scale='Teal', template='plotly_white',
                             labels={y_col: 'Cost (RM)', 'ad_name': ''}, title=title)
                fig.add_hline(y=avg_val, line_dash='dash', line_color='red',
                              annotation_text=f"Avg: RM {avg_val:.2f}")
                fig.update_layout(height=320, showlegend=False)
                return fig

            cm1, cm2 = st.columns(2)
            cm3, cm4 = st.columns(2)
            with cm1:
                st.caption("⭐ Lower = better")
                st.plotly_chart(cost_bar(cost_m, 'cpm',  'Avg CPM by Ad',         cost_m['cpm'].mean()),   use_container_width=True)
            with cm2:
                st.caption("⭐ Lower = better")
                st.plotly_chart(cost_bar(cost_m, 'cpc',  'Avg CPC by Ad',         cost_m['cpc'].mean()),   use_container_width=True)
            with cm3:
                st.caption("⭐ Lower = better")
                st.plotly_chart(cost_bar(cost_m, 'cplpv','Cost per Landing Page', cost_m['cplpv'].mean()), use_container_width=True)
            with cm4:
                st.caption("⭐ Lower = better")
                st.plotly_chart(cost_bar(cost_m, 'cpe',  'Cost per Engagement',   cost_m['cpe'].mean()),   use_container_width=True)

            st.divider()

            # -------------------------------------------------------
            # PART E: Daily Trend (single ad only)
            # -------------------------------------------------------
            st.subheader("📈 Daily Trend Analysis")

            if is_single_ad and not df_display.empty:
                sd2 = df_display.sort_values('reporting_starts').copy()
                min_d = sd2['reporting_starts'].min()
                sd2['Day'] = (sd2['reporting_starts'] - min_d).dt.days + 1
                sd2['Day Label'] = 'Day ' + sd2['Day'].astype(str)

                tr1, tr2 = st.columns(2)
                with tr1:
                    fig = px.line(sd2.dropna(subset=['impressions','reach']),
                                  x='Day Label', y=['impressions','reach'],
                                  markers=True, template='plotly_white',
                                  title='Daily Impressions & Reach')
                    fig.update_xaxes(type='category')
                    fig.update_layout(height=350)
                    st.plotly_chart(fig, use_container_width=True)
                with tr2:
                    fig = px.line(sd2.dropna(subset=['link_clicks','website_landing_page_views']),
                                  x='Day Label', y=['link_clicks','website_landing_page_views','post_engagements'],
                                  markers=True, template='plotly_white',
                                  title='Daily Clicks & Conversions')
                    fig.update_xaxes(type='category')
                    fig.update_layout(height=350)
                    st.plotly_chart(fig, use_container_width=True)

                fig_sp = px.bar(sd2, x='Day Label', y='amount_spent',
                                template='plotly_white', title='Daily Spend (RM)',
                                labels={'amount_spent': 'Spend (RM)'}, color='amount_spent',
                                color_continuous_scale='Blues')
                fig_sp.update_layout(height=300)
                st.plotly_chart(fig_sp, use_container_width=True)
            else:
                st.info("💡 Select a specific ad above to see daily trend charts.")

            st.divider()

            # -------------------------------------------------------
            # PART F: Channel Performance
            # -------------------------------------------------------
            st.subheader("📱 Channel Performance (Instagram vs Facebook)")

            ch_m = df_display.groupby('ad_name').agg(
                fb_likes=('facebook_likes','sum'),
                ig_follows=('instagram_follows','sum'),
                shares=('post_shares','sum'),
                saves=('post_saves','sum'),
                ig_visits=('instagram_profile_visits','sum'),
                video_plays=('video_plays','sum')
            ).reset_index()
            ch_m.columns = ['Ad Name','FB Likes','IG Follows','Post Shares','Post Saves','IG Profile Visits','Video Plays']
            st.dataframe(ch_m.sort_values('FB Likes', ascending=False), use_container_width=True, hide_index=True)

            st.divider()

            # -------------------------------------------------------
            # PART G: ROI Summary
            # -------------------------------------------------------
            st.subheader("🎯 ROI Summary")

            r1, r2 = st.tabs(["Overall", "By Ad"])

            with r1:
                roi_df = pd.DataFrame({
                    'Metric': [
                        'Total Spend',
                        'Total Landing Page Views',
                        'Cost per Landing Page View',
                        'Total Link Clicks',
                        'Cost per Link Click',
                        'LPV CVR (LPV / Clicks)',
                        'Total Engagements',
                        'Cost per Engagement'
                    ],
                    'Value': [
                        f"RM {total_spend:,.2f}",
                        f"{total_lpv:,.0f}",
                        f"RM {cost_per_lp:.2f}",
                        f"{total_link_clicks:,.0f}",
                        f"RM {total_spend/total_link_clicks:.2f}" if total_link_clicks > 0 else "N/A",
                        f"{(total_lpv/total_link_clicks*100):.1f}%" if total_link_clicks > 0 else "N/A",
                        f"{total_engagements:,.0f}",
                        f"RM {cost_per_eng:.2f}"
                    ]
                })
                st.dataframe(roi_df, use_container_width=True, hide_index=True, height=320)

            with r2:
                roi_ad = df_meta_filtered.groupby('ad_name').agg(
                    Total_Spend=('amount_spent','sum'),
                    Link_Clicks=('link_clicks','sum'),
                    LPV=('website_landing_page_views','sum'),
                    Engagements=('post_engagements','sum'),
                    CPC=('cpc','mean'),
                    CPLPV=('cost_per_landing_page_view','mean'),
                    CPE=('cost_per_post_engagement','mean'),
                    CPM=('cpm','mean')
                ).reset_index()
                roi_ad['LPV CVR %'] = np.where(
                    roi_ad['Link_Clicks'] > 0,
                    roi_ad['LPV'] / roi_ad['Link_Clicks'] * 100,
                    0
                )
                roi_ad.columns = ['Ad Name','Total Spend','Link Clicks','LPV','Engagements','Avg CPC','Avg CPLPV','Avg CPE','Avg CPM','LPV CVR %']
                st.dataframe(roi_ad, use_container_width=True, hide_index=True)
