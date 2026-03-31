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

    # --- 2. 过滤主周期数据 ---
    # 【修改】: 基于 df_sales 进行日期过滤（仅日期过滤，无仓库过滤）
    mask_curr = (
        (df_sales['Date'] >= pd.to_datetime(date_range[0])) & 
        (df_sales['Date'] <= pd.to_datetime(date_range[1]))
    )
    df_curr = df_sales[mask_curr].copy()

    # --- 3. 过滤对比周期数据 (如果启用) ---
    df_comp_sidebar = pd.DataFrame()
    if enable_comparison and comp_range and len(comp_range) == 2:
        # 【修改】: 同样基于 df_sales 进行日期过滤
        mask_comp = (
            (df_sales['Date'] >= pd.to_datetime(comp_range[0])) & 
            (df_sales['Date'] <= pd.to_datetime(comp_range[1]))
        )
        df_comp_sidebar = df_sales[mask_comp].copy()

    # --- 4. 准备用于图表的数据 ---
    # 【修改】: df_all_chan 现在自然地包含了已过滤的数据
    df_all_chan = pd.concat([df_comp_sidebar, df_curr], ignore_index=True)
    sorted_months_chan = []
    if not df_all_chan.empty:
        df_all_chan['Month'] = df_all_chan['Date'].dt.to_period('M').astype(str)
        sorted_months_chan = sorted(df_all_chan['Month'].unique())
    
    # --- 5. 渲染逻辑 ---
    if df_curr.empty:
        st.warning("No sales data found for the selected date range and warehouses.")
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
        
        # 【修改】: 基于 df_curr (已过滤)
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
        # PART 3: Channel & Customer Analysis
        # =========================================================
        st.subheader("2. Channel & Customer Analysis")
        ar_col1, col_spacer, ar_col2 = st.columns([1, 0.1, 1])
        
        with ar_col1:
            st.caption("📊 Monthly Revenue Breakdown by Channel (Comparison Mode)")
            # 【修改】: 基于 df_all_chan (已过滤)
            chan_data = df_all_chan.groupby(['AR Type', 'Month'])['Sales'].sum().reset_index()
            fig_ar = px.bar(chan_data, x='AR Type', y='Sales', color='Month', barmode='group', text_auto='.2s', category_orders={"Month": sorted_months_chan}, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_ar.update_layout(height=450, legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig_ar, use_container_width=True)
                    
        with ar_col2:
            st.caption("🏆 Top Customers Analysis")
            
            p_label = f"{date_range[0].strftime('%Y-%m-%d')} to {date_range[1].strftime('%Y-%m-%d')}"
            
            if not enable_comparison or df_comp_sidebar.empty:
                # --- 正常模式 ---
                # 【修改】: 基于 df_curr (已过滤)
                cust_detail = df_curr.groupby(['AR Type', 'AR Name'])['Sales'].sum().reset_index()
                cust_detail = cust_detail.sort_values('Sales', ascending=False).head(50)
                
                st.dataframe(
                    cust_detail, hide_index=True, use_container_width=True, height=400,
                    column_config={"Sales": st.column_config.NumberColumn(p_label, format="RM%.2f")}
                )
            else:
                # --- 对比模式 ---
                c_label = f"{comp_range[0].strftime('%Y-%m-%d')} to {comp_range[1].strftime('%Y-%m-%d')}"
                
                # 【修改】: 基于 df_curr 和 df_comp_sidebar (均已过滤)
                p_sales = df_curr.groupby(['AR Type', 'AR Name'])['Sales'].sum().reset_index().rename(columns={'Sales': p_label})
                c_sales = df_comp_sidebar.groupby(['AR Type', 'AR Name'])['Sales'].sum().reset_index().rename(columns={'Sales': c_label})
                
                cust_detail = pd.merge(p_sales, c_sales, on=['AR Type', 'AR Name'], how='outer').fillna(0)
                # 【修复 KeyError】: 检查列是否存在再进行计算
                if p_label in cust_detail.columns and c_label in cust_detail.columns:
                    cust_detail['Diff'] = cust_detail[p_label] - cust_detail[c_label]
                else:
                    cust_detail['Diff'] = 0
                cust_detail = cust_detail.sort_values(p_label, ascending=False).head(50)
                
                st.dataframe(
                    cust_detail, hide_index=True, use_container_width=True, height=400,
                    column_config={
                        p_label: st.column_config.NumberColumn(p_label, format="RM%.2f"),
                        c_label: st.column_config.NumberColumn(c_label, format="RM%.2f"),
                        "Diff": st.column_config.NumberColumn("Difference", format="RM%.2f")
                    }
                )
        
        # 【注意】: 后续的所有分析，如 "Detailed Customer & Product Breakdown" 和 "Product Performance & Trend Analysis"
        # 都会自动使用已经过全局过滤的 df_curr 或 df_sales，因此无需再做额外修改。
        # 这里我将保持原有的逻辑，因为它已经能正确工作。
        
        st.subheader("2.1 Detailed Customer & Product Breakdown")
        st.caption("💡Displaying data for the [Primary Date Range] only")

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
            st.markdown(f"**Step 2: Customers in {selected_type if selected_type else '...'}**")
            if selected_type:
                name_summary = df_curr[df_curr['AR Type'] == selected_type].groupby('AR Name')[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)
                
                event_name = st.dataframe(
                    name_summary, hide_index=True, use_container_width=True, height=300,
                    on_select="rerun", selection_mode="single-row", key="dd_name_table",
                    column_config={
                        "AR Name": st.column_config.TextColumn("Customer Name"),
                        "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                        "Sales": st.column_config.NumberColumn("Sales", format="RM%.2f")
                    }
                )
            else:
                st.info("Please select an AR Type.")

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
        
        st.subheader("3. Product Performance & Trend Analysis")
        
        curr_month_period = pd.to_datetime(date_range[1]).to_period('M')
        prev_month_period = curr_month_period - 1

        p_top_col1, col_spacer_p, p_top_col2 = st.columns([1, 0.1, 1])
        with p_top_col1:
            st.caption(f"📊 Sales by Category ({curr_month_period})")
            # 【修改】: 基于 df_sales
            cat_sales = df_sales[
                (df_sales['Date'].dt.to_period('M') == curr_month_period)
            ].groupby('Category')['Sales'].sum().reset_index().sort_values('Sales', ascending=False)
            fig_cat = px.pie(cat_sales, values='Sales', names='Category', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_cat.update_layout(height=350, margin=dict(t=30, b=0, l=0, r=0))
            st.plotly_chart(fig_cat, use_container_width=True)

        with p_top_col2:
            st.caption(f"🏆 Top Selling Models ({curr_month_period})")
            
            # 【修改】: 基于 df_sales
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
            st.markdown(f"**Step 3: Customers ( {selected_type_p if selected_type_p else '...'} )**")
            if selected_type_p:
                customer_summary = df_curr[
                    (df_curr['Stock Name'] == selected_model) & 
                    (df_curr['AR Type'] == selected_type_p)
                ].groupby('AR Name')[['Quantity', 'Sales']].sum().reset_index().sort_values('Sales', ascending=False)
                
                st.dataframe(
                    customer_summary, hide_index=True, use_container_width=True, height=400,
                    column_config={
                        "AR Name": st.column_config.TextColumn("Customer Name"),
                        "Quantity": st.column_config.NumberColumn("Units", format="%d"),
                        "Sales": st.column_config.NumberColumn("Customer Sales", format="RM%.2f")
                    }
                )
            else:
                st.info("Please select a Channel Type.")

        st.divider()

        st.caption("📈 Top 20 Models Performance with Sparklines")
        
        # 【修改】: 基于 df_sales
        df_full_history = df_sales[
            (df_sales['Date'].dt.to_period('M') <= curr_month_period)
        ].copy()
        df_full_history['Month_Label'] = df_full_history['Date'].dt.to_period('M').astype(str)
        
        full_months_axis = sorted(df_full_history['Month_Label'].unique())
        
        spark_raw = df_full_history.groupby(['Stock Name', 'Month_Label'])['Quantity'].sum().reset_index()
        spark_pivot = spark_raw.pivot(index='Stock Name', columns='Month_Label', values='Quantity').fillna(0)
        spark_pivot['Trend'] = spark_pivot.values.tolist()
        spark_pivot = spark_pivot.reset_index()

        # 【修改】: 基于 df_sales
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
    st.caption("Optimized analysis with daily average metrics and normalized performance comparison.")
    
    if df_meta_ads_raw.empty:
        st.warning("No data found in the 'meta_ads' table.")
    else:
        # --- 1. 数据预处理 ---
        df_meta_ads = df_meta_ads_raw.copy()
        
        # 确保日期列存在并转换为datetime
        if 'reporting_starts' in df_meta_ads.columns:
            df_meta_ads['reporting_starts'] = pd.to_datetime(df_meta_ads['reporting_starts'], errors='coerce')
        if 'reporting_ends' in df_meta_ads.columns:
            df_meta_ads['reporting_ends'] = pd.to_datetime(df_meta_ads['reporting_ends'], errors='coerce')
        if 'starts' in df_meta_ads.columns:
            df_meta_ads['starts'] = pd.to_datetime(df_meta_ads['starts'], errors='coerce')
        if 'ends' in df_meta_ads.columns:
            df_meta_ads['ends'] = pd.to_datetime(df_meta_ads['ends'], errors='coerce')
        
        # 计算广告活动周期（Ad Period）
        if 'starts' in df_meta_ads.columns and 'ends' in df_meta_ads.columns:
            df_meta_ads['ad_period'] = df_meta_ads.apply(
                lambda row: f"{row['starts'].strftime('%Y-%m-%d')} to {row['ends'].strftime('%Y-%m-%d')}" 
                if pd.notna(row['starts']) and pd.notna(row['ends']) else "N/A",
                axis=1
            )
        
        # 创建日期范围用于过滤（基于reporting_starts）
        if 'reporting_starts' in df_meta_ads.columns:
            meta_ads_min_date = df_meta_ads['reporting_starts'].min()
            meta_ads_max_date = df_meta_ads['reporting_starts'].max()
        else:
            meta_ads_min_date = None
            meta_ads_max_date = None
        
        # --- 2. 侧边栏日期过滤器 ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("Meta Ads Filters")
        
        # 日期范围过滤（基于reporting_starts）
        if meta_ads_min_date and meta_ads_max_date:
            meta_ads_date_range = st.sidebar.date_input(
                "Report Date Range (reporting_starts)",
                value=(meta_ads_min_date.date(), meta_ads_max_date.date()),
                min_value=meta_ads_min_date.date(),
                max_value=meta_ads_max_date.date(),
                key='meta_ads_date_range'
            )
            
            if len(meta_ads_date_range) == 2:
                meta_d1, meta_d2 = pd.to_datetime(meta_ads_date_range[0]), pd.to_datetime(meta_ads_date_range[1])
                df_meta_ads_filtered = df_meta_ads[
                    (df_meta_ads['reporting_starts'] >= meta_d1) & 
                    (df_meta_ads['reporting_starts'] <= meta_d2)
                ].copy()
            else:
                df_meta_ads_filtered = df_meta_ads.copy()
        else:
            df_meta_ads_filtered = df_meta_ads.copy()
        
        # --- 3. TAB内广告名称过滤器 ---
        st.subheader("🎯 Ad Name Filter & Selection")
        
        if 'ad_name' in df_meta_ads_filtered.columns:
            ad_names = sorted(df_meta_ads_filtered['ad_name'].dropna().unique().tolist())
            
            # 创建两列布局
            col_filter, col_info = st.columns([2, 1])
            
            with col_filter:
                # 广告名称过滤 - 单选（用于对比）
                selected_ad = st.selectbox(
                    "Select an Ad Name to analyze:",
                    options=["All Ads"] + ad_names,
                    index=0,
                    key='meta_ads_main_filter',
                    help="Select a specific ad to compare with others, or 'All Ads' to see overall performance"
                )
            
            with col_info:
                st.metric("Total Ads", len(ad_names))
            
            # 根据选择过滤数据
            if selected_ad == "All Ads":
                df_meta_ads_display = df_meta_ads_filtered.copy()
                selected_ad_data = None
                is_single_ad = False
            else:
                df_meta_ads_display = df_meta_ads_filtered.copy()
                selected_ad_data = df_meta_ads_filtered[df_meta_ads_filtered['ad_name'] == selected_ad].copy()
                is_single_ad = True
            
            st.divider()
            
            # ===== 【优化】如果是All Ads，先显示KPI Dashboard =====
            if not is_single_ad:
                st.subheader("📊 Key Performance Indicators")
                
                # 全部广告的KPI（聚合daily数据）
                total_spend = df_meta_ads_display['amount_spent'].sum() if 'amount_spent' in df_meta_ads_display.columns else 0
                total_impressions = df_meta_ads_display['impressions'].sum() if 'impressions' in df_meta_ads_display.columns else 0
                total_reach = df_meta_ads_display['reach'].sum() if 'reach' in df_meta_ads_display.columns else 0
                total_link_clicks = df_meta_ads_display['link_clicks'].sum() if 'link_clicks' in df_meta_ads_display.columns else 0
                total_landing_page_views = df_meta_ads_display['website_landing_page_views'].sum() if 'website_landing_page_views' in df_meta_ads_display.columns else 0
                total_engagements = df_meta_ads_display['post_engagements'].sum() if 'post_engagements' in df_meta_ads_display.columns else 0
                
                avg_cpm = df_meta_ads_display['cpm'].mean() if 'cpm' in df_meta_ads_display.columns else 0
                avg_cpc = df_meta_ads_display['cpc'].mean() if 'cpc' in df_meta_ads_display.columns else 0
                avg_ctr = df_meta_ads_display['ctr'].mean() if 'ctr' in df_meta_ads_display.columns else 0
                avg_frequency = df_meta_ads_display['frequency'].mean() if 'frequency' in df_meta_ads_display.columns else 0
                
                cost_per_landing_page = df_meta_ads_display['cost_per_landing_page_view'].mean() if 'cost_per_landing_page_view' in df_meta_ads_display.columns else 0
                cost_per_engagement = df_meta_ads_display['cost_per_post_engagement'].mean() if 'cost_per_post_engagement' in df_meta_ads_display.columns else 0
                
                # 显示KPI指标
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                
                with col1:
                    st.metric("💰 Total Spend", f"RM {total_spend:,.2f}")
                
                with col2:
                    st.metric("👁️ Total Impressions", f"{total_impressions:,.0f}")
                
                with col3:
                    st.metric("🔗 Link Clicks", f"{total_link_clicks:,.0f}")
                
                with col4:
                    st.metric("📄 Landing Pages", f"{total_landing_page_views:,.0f}")
                
                with col5:
                    st.metric("💬 Engagements", f"{total_engagements:,.0f}")
                
                with col6:
                    st.metric("📊 Reach", f"{total_reach:,.0f}")
                
                st.divider()
            
            # --- 4. 广告周期信息 ---
            if is_single_ad and not selected_ad_data.empty:
                st.subheader("📅 Ad Campaign Period")
                
                col_period1, col_period2 = st.columns(2)
                
                with col_period1:
                    if 'starts' in selected_ad_data.columns:
                        campaign_start = selected_ad_data['starts'].min()
                        st.metric("Campaign Start Date", campaign_start.strftime('%Y-%m-%d') if pd.notna(campaign_start) else "N/A")
                
                with col_period2:
                    if 'ends' in selected_ad_data.columns:
                        campaign_end = selected_ad_data['ends'].max()
                        st.metric("Campaign End Date", campaign_end.strftime('%Y-%m-%d') if pd.notna(campaign_end) else "N/A")
                
                st.divider()
                
                # ===== 【优化】如果是Selected Ad，在Ad Campaign Period下显示KPI Dashboard =====
                st.subheader("📊 Key Performance Indicators")
                
                # 计算选中广告的KPI（聚合daily数据）
                total_spend = selected_ad_data['amount_spent'].sum() if 'amount_spent' in selected_ad_data.columns else 0
                total_impressions = selected_ad_data['impressions'].sum() if 'impressions' in selected_ad_data.columns else 0
                total_reach = selected_ad_data['reach'].sum() if 'reach' in selected_ad_data.columns else 0
                total_link_clicks = selected_ad_data['link_clicks'].sum() if 'link_clicks' in selected_ad_data.columns else 0
                total_landing_page_views = selected_ad_data['website_landing_page_views'].sum() if 'website_landing_page_views' in selected_ad_data.columns else 0
                total_engagements = selected_ad_data['post_engagements'].sum() if 'post_engagements' in selected_ad_data.columns else 0
                
                avg_cpm = selected_ad_data['cpm'].mean() if 'cpm' in selected_ad_data.columns else 0
                avg_cpc = selected_ad_data['cpc'].mean() if 'cpc' in selected_ad_data.columns else 0
                avg_ctr = selected_ad_data['ctr'].mean() if 'ctr' in selected_ad_data.columns else 0
                avg_frequency = selected_ad_data['frequency'].mean() if 'frequency' in selected_ad_data.columns else 0
                
                cost_per_landing_page = selected_ad_data['cost_per_landing_page_view'].mean() if 'cost_per_landing_page_view' in selected_ad_data.columns else 0
                cost_per_engagement = selected_ad_data['cost_per_post_engagement'].mean() if 'cost_per_post_engagement' in selected_ad_data.columns else 0
                
                # 显示KPI指标
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                
                with col1:
                    st.metric("💰 Total Spend", f"RM {total_spend:,.2f}")
                
                with col2:
                    st.metric("👁️ Total Impressions", f"{total_impressions:,.0f}")
                
                with col3:
                    st.metric("🔗 Link Clicks", f"{total_link_clicks:,.0f}")
                
                with col4:
                    st.metric("📄 Landing Pages", f"{total_landing_page_views:,.0f}")
                
                with col5:
                    st.metric("💬 Engagements", f"{total_engagements:,.0f}")
                
                with col6:
                    st.metric("📊 Reach", f"{total_reach:,.0f}")
                
                st.divider()
            
            # ===== AD PERFORMANCE RANKING WITH DAILY AVERAGE METRICS =====
            st.subheader("🏆 Ad Performance Ranking")
            
            if 'ad_name' in df_meta_ads_display.columns:
                # 按广告名称分组汇总
                ad_summary = df_meta_ads_display.groupby('ad_name').agg({
                    'amount_spent': 'sum',
                    'impressions': 'sum',
                    'reach': 'sum',
                    'link_clicks': 'sum',
                    'website_landing_page_views': 'sum',
                    'post_engagements': 'sum',
                    'cpm': 'mean',
                    'cpc': 'mean',
                    'ctr': 'mean',
                    'starts': 'min',
                    'ends': 'max'
                }).reset_index()
                
                # 计算运行天数
                ad_summary['Days Running'] = (ad_summary['ends'] - ad_summary['starts']).dt.days + 1
                
                # 计算日均指标
                ad_summary['Daily Avg Spend'] = ad_summary['amount_spent'] / ad_summary['Days Running']
                ad_summary['Daily Avg Impressions'] = ad_summary['impressions'] / ad_summary['Days Running']
                ad_summary['Daily Avg Clicks'] = ad_summary['link_clicks'] / ad_summary['Days Running']
                ad_summary['Daily Avg Landing Pages'] = ad_summary['website_landing_page_views'] / ad_summary['Days Running']
                
                # 按Total Spend排序
                ad_summary = ad_summary.sort_values('amount_spent', ascending=False).reset_index(drop=True)
                ad_summary['Rank'] = range(1, len(ad_summary) + 1)
                
                # 添加排名标记
                rank_marks = {1: '🥇', 2: '🥈', 3: '🥉'}
                ad_summary['Rank Mark'] = ad_summary['Rank'].apply(lambda x: rank_marks.get(x, f'#{x}'))
                
                # 显示表格
                display_df = ad_summary[[
                    'Rank Mark', 'ad_name', 'Days Running',
                    'Daily Avg Spend', 'amount_spent',
                    'Daily Avg Impressions', 'impressions',
                    'Daily Avg Clicks', 'link_clicks',
                    'Daily Avg Landing Pages', 'website_landing_page_views',
                    'cpm', 'cpc', 'ctr'
                ]].copy()
                
                display_df.columns = [
                    'Rank', 'Ad Name', 'Days', 'Daily Avg Spend', 'Total Spend',
                    'Daily Avg Impressions', 'Total Impressions', 
                    'Daily Avg Clicks', 'Total Clicks',
                    'Daily Avg Landing Pages', 'Total Landing Pages',
                    'Avg CPM', 'Avg CPC', 'Avg CTR'
                ]
                
                # 格式化数值
                display_df['Daily Avg Spend'] = display_df['Daily Avg Spend'].apply(lambda x: f"RM {x:,.2f}")
                display_df['Total Spend'] = display_df['Total Spend'].apply(lambda x: f"RM {x:,.2f}")
                display_df['Daily Avg Impressions'] = display_df['Daily Avg Impressions'].apply(lambda x: f"{x:,.0f}")
                display_df['Total Impressions'] = display_df['Total Impressions'].apply(lambda x: f"{x:,.0f}")
                display_df['Daily Avg Clicks'] = display_df['Daily Avg Clicks'].apply(lambda x: f"{x:,.0f}")
                display_df['Total Clicks'] = display_df['Total Clicks'].apply(lambda x: f"{x:,.0f}")
                display_df['Daily Avg Landing Pages'] = display_df['Daily Avg Landing Pages'].apply(lambda x: f"{x:,.0f}")
                display_df['Total Landing Pages'] = display_df['Total Landing Pages'].apply(lambda x: f"{x:,.0f}")
                display_df['Avg CPM'] = display_df['Avg CPM'].apply(lambda x: f"RM {x:,.2f}")
                display_df['Avg CPC'] = display_df['Avg CPC'].apply(lambda x: f"RM {x:,.2f}")
                display_df['Avg CTR'] = display_df['Avg CTR'].apply(lambda x: f"{x:.2%}")
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # ===== 【新增】TAB 2: NORMALIZED PERFORMANCE TABLE =====
            st.subheader("💡 Normalized Performance - If Spending RM 100 per Ad")
            
            if 'ad_name' in df_meta_ads_display.columns:
                # 计算规范化指标（假设花RM100）
                normalized_data = df_meta_ads_display.groupby('ad_name').agg({
                    'amount_spent': 'sum',
                    'impressions': 'sum',
                    'reach': 'sum',
                    'link_clicks': 'sum',
                    'website_landing_page_views': 'sum',
                    'post_engagements': 'sum',
                    'instagram_profile_visits': 'sum',
                    'instagram_follows': 'sum',
                    'facebook_likes': 'sum',
                    'video_plays': 'sum'
                }).reset_index()
                
                # 计算规范化指标（基于RM100）
                budget_baseline = 100
                
                normalized_data['Impressions per RM100'] = (normalized_data['impressions'] / normalized_data['amount_spent'] * budget_baseline).round(0)
                normalized_data['Reach per RM100'] = (normalized_data['reach'] / normalized_data['amount_spent'] * budget_baseline).round(0)
                normalized_data['Clicks per RM100'] = (normalized_data['link_clicks'] / normalized_data['amount_spent'] * budget_baseline).round(0)
                normalized_data['Landing Pages per RM100'] = (normalized_data['website_landing_page_views'] / normalized_data['amount_spent'] * budget_baseline).round(0)
                normalized_data['Engagements per RM100'] = (normalized_data['post_engagements'] / normalized_data['amount_spent'] * budget_baseline).round(0)
                normalized_data['IG Visits per RM100'] = (normalized_data['instagram_profile_visits'] / normalized_data['amount_spent'] * budget_baseline).round(0)
                normalized_data['IG Follows per RM100'] = (normalized_data['instagram_follows'] / normalized_data['amount_spent'] * budget_baseline).round(0)
                normalized_data['FB Likes per RM100'] = (normalized_data['facebook_likes'] / normalized_data['amount_spent'] * budget_baseline).round(0)
                normalized_data['Video Plays per RM100'] = (normalized_data['video_plays'] / normalized_data['amount_spent'] * budget_baseline).round(0)
                
                # 显示表格
                normalized_display = normalized_data[[
                    'ad_name',
                    'Impressions per RM100',
                    'Reach per RM100',
                    'Clicks per RM100',
                    'Landing Pages per RM100',
                    'Engagements per RM100',
                    'IG Visits per RM100',
                    'IG Follows per RM100',
                    'FB Likes per RM100',
                    'Video Plays per RM100'
                ]].copy()
                
                normalized_display.columns = [
                    'Ad Name',
                    'Impressions',
                    'Reach',
                    'Clicks',
                    'Landing Pages',
                    'Engagements',
                    'IG Visits',
                    'IG Follows',
                    'FB Likes',
                    'Video Plays'
                ]
                
                # 排序（按impressions降序）
                normalized_display = normalized_display.sort_values('Impressions', ascending=False).reset_index(drop=True)
                
                st.dataframe(normalized_display, use_container_width=True, hide_index=True)
                
                # 添加说明
                st.info(
                    "💡 **说明**：此表格显示如果每个广告都花费RM100，各个指标的预期表现。"
                    "这样可以公平对比不同预算的广告。"
                )
            
            st.divider()
            
            # --- 6. 成本指标对比 ---
            st.subheader("💰 Cost Metrics Comparison by Ad")
            
            if 'ad_name' in df_meta_ads_display.columns:
                # 按广告分组计算成本指标
                cost_metrics = df_meta_ads_display.groupby('ad_name').agg({
                    'cpm': 'mean',
                    'cpc': 'mean',
                    'cost_per_landing_page_view': 'mean',
                    'cost_per_post_engagement': 'mean'
                }).reset_index()
                
                cost_metrics = cost_metrics.sort_values('cpm', ascending=True)
                
                # 计算平均值
                avg_cpm = cost_metrics['cpm'].mean()
                avg_cpc = cost_metrics['cpc'].mean()
                avg_cplpv = cost_metrics['cost_per_landing_page_view'].mean()
                avg_cpe = cost_metrics['cost_per_post_engagement'].mean()
                
                # 创建4个图表
                col1, col2 = st.columns(2)
                
                with col1:
                    # Avg CPM
                    st.markdown("**Average CPM by Ad**")
                    st.caption("⭐ 柱子越低 = 每1000次展示的成本越低 = 效率越高")
                    fig_cpm = px.bar(
                        cost_metrics,
                        x='ad_name',
                        y='cpm',
                        template='plotly_white',
                        title='',
                        labels={'cpm': 'CPM (RM)', 'ad_name': 'Ad Name'},
                        color='cpm',
                        color_continuous_scale='Teal'
                    )
                    fig_cpm.add_hline(y=avg_cpm, line_dash="dash", line_color="red", annotation_text=f"Avg: RM {avg_cpm:.2f}")
                    st.plotly_chart(fig_cpm, use_container_width=True)
                
                with col2:
                    # Avg CPC
                    st.markdown("**Average CPC by Ad**")
                    st.caption("⭐ 柱子越低 = 每次点击的成本越低 = 效率越高")
                    fig_cpc = px.bar(
                        cost_metrics,
                        x='ad_name',
                        y='cpc',
                        template='plotly_white',
                        title='',
                        labels={'cpc': 'CPC (RM)', 'ad_name': 'Ad Name'},
                        color='cpc',
                        color_continuous_scale='Teal'
                    )
                    fig_cpc.add_hline(y=avg_cpc, line_dash="dash", line_color="red", annotation_text=f"Avg: RM {avg_cpc:.2f}")
                    st.plotly_chart(fig_cpc, use_container_width=True)
                
                col3, col4 = st.columns(2)
                
                with col3:
                    # Avg CPLPV
                    st.markdown("**Average Cost per Landing Page by Ad**")
                    st.caption("⭐ 柱子越低 = 转化成本越低 = ROI越好")
                    fig_cplpv = px.bar(
                        cost_metrics,
                        x='ad_name',
                        y='cost_per_landing_page_view',
                        template='plotly_white',
                        title='',
                        labels={'cost_per_landing_page_view': 'Cost (RM)', 'ad_name': 'Ad Name'},
                        color='cost_per_landing_page_view',
                        color_continuous_scale='Teal'
                    )
                    fig_cplpv.add_hline(y=avg_cplpv, line_dash="dash", line_color="red", annotation_text=f"Avg: RM {avg_cplpv:.2f}")
                    st.plotly_chart(fig_cplpv, use_container_width=True)
                
                with col4:
                    # Avg CPE
                    st.markdown("**Average Cost per Engagement by Ad**")
                    st.caption("⭐ 柱子越低 = 每次互动的成本越低 = 效率越高")
                    fig_cpe = px.bar(
                        cost_metrics,
                        x='ad_name',
                        y='cost_per_post_engagement',
                        template='plotly_white',
                        title='',
                        labels={'cost_per_post_engagement': 'Cost (RM)', 'ad_name': 'Ad Name'},
                        color='cost_per_post_engagement',
                        color_continuous_scale='Teal'
                    )
                    fig_cpe.add_hline(y=avg_cpe, line_dash="dash", line_color="red", annotation_text=f"Avg: RM {avg_cpe:.2f}")
                    st.plotly_chart(fig_cpe, use_container_width=True)
            
            st.divider()
            
            # --- 7. Daily Trend Analysis ---
            st.subheader("📈 Daily Trend Analysis")
            
            if is_single_ad and selected_ad_data is not None and not selected_ad_data.empty:
                selected_data = selected_ad_data.copy()
                
                # 确保reporting_starts存在
                if 'reporting_starts' in selected_data.columns:
                    selected_data = selected_data.sort_values('reporting_starts')
                    
                    # 计算Day 1, 2, 3...
                    min_date = selected_data['reporting_starts'].min()
                    selected_data['Day Number'] = (selected_data['reporting_starts'] - min_date).dt.days + 1
                    selected_data['Day Label'] = 'Day ' + selected_data['Day Number'].astype(str)
                    
                    # 创建两个图表
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # 展示和覆盖趋势
                        if 'impressions' in selected_data.columns and 'reach' in selected_data.columns:
                            # 准备数据
                            trend_data = selected_data[['Day Label', 'impressions', 'reach']].copy()
                            trend_data = trend_data.dropna(subset=['impressions', 'reach'])
                            
                            if not trend_data.empty:
                                fig_spend = px.line(
                                    trend_data,
                                    x='Day Label',
                                    y=['impressions', 'reach'],
                                    markers=True,
                                    template='plotly_white',
                                    title='Daily Impressions & Reach Trend',
                                    labels={'value': 'Value', 'variable': 'Metric'}
                                )
                                fig_spend.update_xaxes(type='category')
                                st.plotly_chart(fig_spend, use_container_width=True)
                            else:
                                st.warning("No data available for Spend & Impressions trend")
                    
                    with col2:
                        # 转化指标趋势
                        if 'link_clicks' in selected_data.columns and 'website_landing_page_views' in selected_data.columns:
                            # 准备数据
                            conversion_data = selected_data[['Day Label', 'link_clicks', 'website_landing_page_views', 'post_engagements']].copy()
                            conversion_data = conversion_data.dropna(subset=['link_clicks', 'website_landing_page_views'])
                            
                            if not conversion_data.empty:
                                fig_conversion = px.line(
                                    conversion_data,
                                    x='Day Label',
                                    y=['link_clicks', 'website_landing_page_views', 'post_engagements'],
                                    markers=True,
                                    template='plotly_white',
                                    title='Daily Conversion Metrics Trend',
                                    labels={'value': 'Count', 'variable': 'Metric'}
                                )
                                fig_conversion.update_xaxes(type='category')
                                st.plotly_chart(fig_conversion, use_container_width=True)
                            else:
                                st.warning("No data available for Conversion metrics trend")
                else:
                    st.warning("reporting_starts column not found in data")
            else:
                st.info("💡 **提示**: 请在顶部选择一个具体的广告名称来查看Daily Trend Analysis。选择'All Ads'时不显示趋势图表。")
            
            st.divider()
            
            # --- 7.5 Channel Performance (Instagram vs Facebook) ---
            st.subheader("📱 Channel Performance (Instagram vs Facebook)")

            if 'ad_name' in df_meta_ads_display.columns:
                # 按广告分组计算渠道指标
                channel_metrics = df_meta_ads_display.groupby('ad_name').agg({
                    'facebook_likes': 'sum',
                    'instagram_follows': 'sum',
                    'post_shares': 'sum',
                    'post_saves': 'sum',
                    'instagram_profile_visits': 'sum',
                    'video_plays': 'sum'
                }).reset_index()
                
                # 重命名列
                channel_metrics = channel_metrics.rename(columns={
                    'facebook_likes': 'Facebook Likes',
                    'instagram_follows': 'Instagram Follows',
                    'post_shares': 'Post Shares',
                    'post_saves': 'Post Saves',
                    'instagram_profile_visits': 'IG Profile Visits',
                    'video_plays': 'Video Plays'
                })
                
                # 按Facebook Likes排序
                channel_metrics = channel_metrics.sort_values('Facebook Likes', ascending=False).reset_index(drop=True)
                
                st.dataframe(channel_metrics, use_container_width=True, hide_index=True)
                
                st.info(
                    "💡 **说明**：此表格显示每个广告在Instagram和Facebook上的互动指标。"
                    "可以帮助您了解不同渠道的表现差异。"
                )

            st.divider()

            
            # --- 8. ROI & Conversion Analysis ---
            st.subheader("🎯 ROI & Conversion Analysis")
            
            roi_tab1, roi_tab2 = st.tabs(["Overall", "Ad Comparison"])
            
            with roi_tab1:
                if 'amount_spent' in df_meta_ads_display.columns and 'website_landing_page_views' in df_meta_ads_display.columns:
                    roi_metrics = pd.DataFrame({
                        'Metric': [
                            'Total Spend',
                            'Landing Page Views',
                            'Cost per Landing Page View',
                            'Link Clicks',
                            'Cost per Link Click',
                            'Total Engagements',
                            'Cost per Engagement'
                        ],
                        'Value': [
                            f"RM {total_spend:,.2f}",
                            f"{total_landing_page_views:,.0f}",
                            f"RM {cost_per_landing_page:.2f}",
                            f"{total_link_clicks:,.0f}",
                            f"RM {total_spend/total_link_clicks:.2f}" if total_link_clicks > 0 else "N/A",
                            f"{total_engagements:,.0f}",
                            f"RM {cost_per_engagement:.2f}"
                        ]
                    })
                    
                    st.dataframe(roi_metrics, use_container_width=True, hide_index=True, height=300)
            
            with roi_tab2:
                st.markdown("**ROI & Conversion by Ad Name**")
                
                if 'ad_name' in df_meta_ads_display.columns:
                    # 按ad_name汇总ROI数据
                    roi_by_ad = df_meta_ads_display.groupby('ad_name').agg({
                        'amount_spent': 'sum',
                        'link_clicks': 'sum',
                        'website_landing_page_views': 'sum',
                        'post_engagements': 'sum',
                        'cpc': 'mean',
                        'cost_per_landing_page_view': 'mean',
                        'cost_per_post_engagement': 'mean',
                        'cpm': 'mean'
                    }).reset_index()
                    
                    roi_by_ad.columns = [
                        'Ad Name', 'Total Spend', 'Link Clicks', 'Landing Page Views',
                        'Engagements', 'Cost per Click', 'Cost per Landing Page',
                        'Cost per Engagement', 'Avg CPM'
                    ]
                    
                    st.dataframe(roi_by_ad, use_container_width=True, hide_index=True, height=300)
                    
                    st.divider()
                    
                    # --- 自由选择轴的对比Line Chart ---
                    st.markdown("**Custom Comparison Line Chart**")
                    
                    # 可用的指标列表
                    available_metrics = ['Total Spend', 'Link Clicks', 'Landing Page Views', 'Engagements', 
                                        'Cost per Click', 'Cost per Landing Page', 'Cost per Engagement', 'Avg CPM']
                    
                    col_select1, col_select2 = st.columns(2)
                    
                    with col_select1:
                        selected_x_metric = st.selectbox(
                            "Select X-Axis Metric:",
                            options=available_metrics,
                            index=0,
                            key='roi_x_axis'
                        )
                    
                    with col_select2:
                        selected_y_metric = st.selectbox(
                            "Select Y-Axis Metric:",
                            options=available_metrics,
                            index=4,  # 默认选择Cost per Click
                            key='roi_y_axis'
                        )
                    
                    # 创建自定义line chart
                    if selected_x_metric and selected_y_metric:
                        # 准备数据
                        chart_data = roi_by_ad[['Ad Name', selected_x_metric, selected_y_metric]].copy()
                        chart_data = chart_data.sort_values(selected_x_metric)
                        
                        # 创建line chart
                        fig_custom = px.line(
                            chart_data,
                            x=selected_x_metric,
                            y=selected_y_metric,
                            markers=True,
                            template='plotly_white',
                            title=f'{selected_y_metric} vs {selected_x_metric}',
                            labels={selected_x_metric: selected_x_metric, selected_y_metric: selected_y_metric},
                            hover_data={'Ad Name': True}
                        )
                        
                        # 添加平均值线
                        avg_y = chart_data[selected_y_metric].mean()
                        fig_custom.add_hline(
                            y=avg_y,
                            line_dash="dash",
                            line_color="red",
                            annotation_text=f"Average: {avg_y:.2f}",
                            annotation_position="right"
                        )
                        
                        # 标记每个点的广告名称
                        fig_custom.update_traces(
                            text=chart_data['Ad Name'],
                            textposition="top center",
                            mode='lines+markers+text'
                        )
                        
                        fig_custom.update_traces(line_width=2, marker_size=8)
                        
                        st.plotly_chart(fig_custom, use_container_width=True)
                        
                        # 显示统计信息
                        col_stat1, col_stat2, col_stat3 = st.columns(3)
                        
                        with col_stat1:
                            st.metric(
                                f"Average {selected_y_metric}",
                                f"{avg_y:.2f}" if isinstance(avg_y, (int, float)) else avg_y
                            )
                        
                        with col_stat2:
                            min_val = chart_data[selected_y_metric].min()
                            min_ad = chart_data[chart_data[selected_y_metric] == min_val]['Ad Name'].values[0]
                            st.metric(
                                f"Lowest {selected_y_metric}",
                                f"{min_val:.2f}" if isinstance(min_val, (int, float)) else min_val,
                                f"({min_ad})"
                            )
                        
                        with col_stat3:
                            max_val = chart_data[selected_y_metric].max()
                            max_ad = chart_data[chart_data[selected_y_metric] == max_val]['Ad Name'].values[0]
                            st.metric(
                                f"Highest {selected_y_metric}",
                                f"{max_val:.2f}" if isinstance(max_val, (int, float)) else max_val,
                                f"({max_ad})"
                            )
            st.divider()
            
            # --- 成本对比图表 ---
            if is_single_ad:
                st.subheader("💰 Cost Comparison - Selected Ad vs Others")
                
                # 准备对比数据
                cost_comparison = pd.DataFrame({
                    'Metric': ['Avg CPM', 'Avg CPC', 'Avg CPLPV', 'Avg Cost/Engagement'],
                    selected_ad: [
                        avg_cpm,
                        avg_cpc,
                        cost_per_landing_page,
                        cost_per_engagement
                    ]
                })
                
                other_ads_data = df_meta_ads_filtered[df_meta_ads_filtered['ad_name'] != selected_ad].copy()
                if not other_ads_data.empty:
                    cost_comparison['Other Ads Avg'] = [
                        other_ads_data['cpm'].mean() if 'cpm' in other_ads_data.columns else 0,
                        other_ads_data['cpc'].mean() if 'cpc' in other_ads_data.columns else 0,
                        other_ads_data['cost_per_landing_page_view'].mean() if 'cost_per_landing_page_view' in other_ads_data.columns else 0,
                        other_ads_data['cost_per_post_engagement'].mean() if 'cost_per_post_engagement' in other_ads_data.columns else 0
                    ]
                    
                    # 创建对比图表
                    fig_cost = px.bar(
                        cost_comparison,
                        x='Metric',
                        y=[selected_ad, 'Other Ads Avg'],
                        barmode='group',
                        template='plotly_white',
                        title=f'Cost Metrics: {selected_ad} vs Other Ads',
                        labels={'value': 'Cost (RM)', 'variable': 'Ad Group'}
                    )
                    st.plotly_chart(fig_cost, use_container_width=True)
