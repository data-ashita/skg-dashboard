import streamlit as st
import pandas as pd
import numpy as np
from supabase import create_client
import io

# --- 1. 页面配置 ---
st.set_page_config(page_title="SKG Data Management", layout="wide")

# 检查登录状态 (确保主页已处理登录逻辑)
if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
    st.warning("Please login on the Home page first.")
    st.stop()

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

# --- 2. 辅助函数 ---

# 获取动态下拉选项
def get_dynamic_options():
    try:
        ar_types = supabase.table("ar_type_settings").select("type_name").execute()
        wh_types = supabase.table("wh_type_settings").select("type_name").execute()
        ar_list = [item['type_name'] for item in ar_types.data]
        wh_list = [item['type_name'] for item in wh_types.data]
        return ar_list, wh_list
    except:
        return [], []

# 生成 Excel 模板
def generate_template(cols):
    output = io.BytesIO()
    pd.DataFrame(columns=cols).to_excel(output, index=False)
    return output.getvalue()

def get_latest_date_in_db(table_name):
    try:
        # 查询 Date 列，按倒序排列取第 1 条数据
        res = supabase.table(table_name).select("Date").order("Date", desc=True).limit(1).execute()
        if res.data:
            return res.data[0]['Date']
        return "No Data"
    except Exception:
        return "Error"

# 获取当前选项
ALLOWED_AR_TYPES, ALLOWED_WH_TYPES = get_dynamic_options()

st.title("📤 Data Management Center")

# --- 3. 业务数据同步 (Transactional Data) ---
st.header("1. Sync Transactional Data")

# Define columns for Excel templates
stock_excel_cols = ["Date", "Stock Code", "Stock Name", "Warehouse Code", "Warehouse Name", "Quantity"]
sales_excel_cols = ["CoID", "Invoice Number", "Stock Code", "Stock Name", "Quantity", "Unit Price", "Sales", "Date", "Warehouse", "Warehouse Name", "AR Code", "AR Name"]

# Helper function to get latest date (Internal function)
def get_latest_date(table_name):
    try:
        res = supabase.table(table_name).select("Date").order("Date", desc=True).limit(1).execute()
        return res.data[0]['Date'] if res.data else "No Data"
    except:
        return "Unknown"

col1, col2 = st.columns(2)

# --- STOCK TABLE SYNC ---
st.header("1. Sync Transactional Data")

# Define columns for Excel templates
stock_excel_cols = ["Date", "Stock Code", "Stock Name", "Warehouse Code", "Warehouse Name", "Quantity"]
sales_excel_cols = ["CoID", "Invoice Number", "Stock Code", "Stock Name", "Quantity", "Unit Price", "Sales", "Date", "Warehouse", "Warehouse Name", "AR Code", "AR Name"]

# Helper function to get latest date from DB
def get_latest_date(table_name):
    try:
        res = supabase.table(table_name).select("Date").order("Date", desc=True).limit(1).execute()
        return res.data[0]['Date'] if res.data else "No Data"
    except:
        return "Unknown"

# Fetch latest options for types
ALLOWED_AR_TYPES, ALLOWED_WH_TYPES = get_dynamic_options()

col1, col2 = st.columns(2)

# ==========================================
# COLUMN 1: STOCK TABLE SYNC
# ==========================================
with col1:
    st.subheader("Sync Stock Table")
    
    # HTML 卡片：显示数据库最新日期
    latest_stock = get_latest_date("stock")
    st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 10px 20px; border-radius: 10px; border-left: 5px solid #007bff; margin-bottom: 15px;">
            <span style="color: #555; font-size: 0.9rem;">Latest Stock Snapshot:</span><br>
            <strong style="color: #007bff; font-size: 1.2rem;">{latest_stock}</strong>
        </div>
    """, unsafe_allow_html=True)
    
    st.download_button("📥 Download Stock Template", generate_template(stock_excel_cols), "stock_template.xlsx")
    f_stock = st.file_uploader("Upload Stock Excel", type=['xlsx'], key="up_stock")
    
    if f_stock and st.button("Sync Stock Data"):
        df = pd.read_excel(f_stock)
        df.columns = df.columns.str.strip()
        
        # 1. 基础清洗：转大写、去空格、强制 Code 为字符串（防止匹配失败）
        df['Warehouse Code'] = df['Warehouse Code'].astype(str).str.strip()
        if 'Warehouse Name' in df.columns:
            df['Warehouse Name'] = df['Warehouse Name'].astype(str).str.upper().str.strip()
        
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        else:
            st.error("❌ ERROR: 'Date' column is missing in Excel.")
            st.stop()

        # 2. 匹配仓库主表
        wh_ref_raw = supabase.table("warehouse").select("warehouse_code, warehouse_name, warehouse_type").execute()
        wh_ref = pd.DataFrame(wh_ref_raw.data)
        
        if not wh_ref.empty:
            wh_ref['warehouse_code'] = wh_ref['warehouse_code'].astype(str).str.strip()
            wh_ref['warehouse_name'] = wh_ref['warehouse_name'].astype(str).str.upper().str.strip()
            # 匹配（基于 Code + Name 确保双重准确）
            df = df.merge(wh_ref, left_on=['Warehouse Code', 'Warehouse Name'], right_on=['warehouse_code', 'warehouse_name'], how='left')
        
        # --- QUICK FIX: 处理缺失的仓库 ---
        mismatched_wh = df[df['warehouse_type'].isna()].copy()
        if not mismatched_wh.empty:
            st.warning("⚠️ Mismatch Detected: New Warehouses found in Excel.")
            missing_df = mismatched_wh[['Warehouse Code', 'Warehouse Name']].drop_duplicates()
            missing_df = missing_df.rename(columns={'Warehouse Code': 'warehouse_code', 'Warehouse Name': 'warehouse_name'})
            missing_df['warehouse_type'] = ALLOWED_WH_TYPES[0] if ALLOWED_WH_TYPES else ""

            # 数据编辑器：允许预览、修改 Type、删除无效项
            edited_fix = st.data_editor(
                missing_df,
                column_config={
                    "warehouse_type": st.column_config.SelectboxColumn("Assign Type", options=ALLOWED_WH_TYPES, required=True),
                    "warehouse_code": "Code", "warehouse_name": "Name"
                },
                num_rows="dynamic", hide_index=True, use_container_width=True, key="wh_fix_stock"
            )

            if st.button("➕ Confirm & Add to Warehouse Master"):
                if not edited_fix.empty:
                    # 插入前二次清洗
                    to_insert = edited_fix.copy()
                    to_insert['warehouse_name'] = to_insert['warehouse_name'].astype(str).str.upper().str.strip()
                    to_insert['warehouse_code'] = to_insert['warehouse_code'].astype(str).str.strip()
                    supabase.table("warehouse").insert(to_insert.to_dict(orient='records')).execute()
                    st.success("Master Data updated! Please click 'Sync Stock Data' again.")
                    st.rerun()
            st.stop()

        # 3. 最终上传（按日期清空重载）
        try:
            df = df.rename(columns={'warehouse_type': 'Warehouse Type'}).drop(columns=['warehouse_code', 'warehouse_name'])
            unique_dates = df['Date'].unique().tolist()
            with st.spinner(f"Replacing stock data for: {unique_dates}"):
                supabase.table("stock").delete().in_("Date", unique_dates).execute()
                supabase.table("stock").insert(df.replace({np.nan: None}).to_dict(orient='records')).execute()
            st.success(f"Stock Synced! (Dates updated: {unique_dates})")
            st.rerun()
        except Exception as e:
            st.error(f"Sync failed: {e}")

# ==========================================
# COLUMN 2: SALES TABLE SYNC
# ==========================================
with col2:
    st.subheader("Sync Sales Table")
    
    # HTML 卡片：显示数据库最新日期
    latest_sales = get_latest_date("sales")
    st.markdown(f"""
        <div style="background-color: #f0f2f6; padding: 10px 20px; border-radius: 10px; border-left: 5px solid #ff4b4b; margin-bottom: 15px;">
            <span style="color: #555; font-size: 0.9rem;">Latest Sales Record:</span><br>
            <strong style="color: #ff4b4b; font-size: 1.2rem;">{latest_sales}</strong>
        </div>
    """, unsafe_allow_html=True)
    
    st.download_button("📥 Download Sales Template", generate_template(sales_excel_cols), "sales_template.xlsx")
    f_sales = st.file_uploader("Upload Sales Excel", type=['xlsx'], key="up_sales")
    
    if f_sales and st.button("Sync Sales Data"):
        df = pd.read_excel(f_sales)
        df.columns = df.columns.str.strip()
        
        # 1. 基础清洗：强制 Code 为文本，名字转大写
        df['AR Code'] = df['AR Code'].astype(str).str.strip()
        df['Warehouse'] = df['Warehouse'].astype(str).str.strip() # 销售表中的仓库 Code
        for col in ['Warehouse Name', 'AR Name']:
            if col in df.columns: df[col] = df[col].astype(str).str.upper().str.strip()
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')

        # 2. 匹配 AR 主表
        ar_db = pd.DataFrame(supabase.table("ar").select("ar_code, ar_name, ar_type").execute().data)
        if not ar_db.empty:
            ar_db['ar_code'] = ar_db['ar_code'].astype(str).str.strip()
            ar_db['ar_name'] = ar_db['ar_name'].astype(str).str.upper().str.strip()
            df = df.merge(ar_db, left_on=['AR Code', 'AR Name'], right_on=['ar_code', 'ar_name'], how='left')

        # --- QUICK FIX 1: 缺失的客户 (AR) ---
        missing_ar_rows = df[df['ar_type'].isna()].copy()
        if not missing_ar_rows.empty:
            st.warning("⚠️ Mismatch Detected: New Customers (AR) found.")
            missing_ar_df = missing_ar_rows[['AR Code', 'AR Name']].drop_duplicates()
            missing_ar_df = missing_ar_df.rename(columns={'AR Code': 'ar_code', 'AR Name': 'ar_name'})
            missing_ar_df['ar_type'] = ALLOWED_AR_TYPES[0] if ALLOWED_AR_TYPES else ""

            edited_ar = st.data_editor(
                missing_ar_df,
                column_config={"ar_type": st.column_config.SelectboxColumn("AR Type", options=ALLOWED_AR_TYPES, required=True)},
                num_rows="dynamic", hide_index=True, key="ar_fix_editor"
            )
            if st.button("➕ Quick Add to AR Master"):
                supabase.table("ar").insert(edited_ar.to_dict(orient='records')).execute()
                st.rerun()
            st.stop()

        # 3. 匹配仓库主表（Sales 表同样需要验证仓库）
        wh_db = pd.DataFrame(supabase.table("warehouse").select("warehouse_code, warehouse_name, warehouse_type").execute().data)
        if not wh_db.empty:
            wh_db['warehouse_code'] = wh_db['warehouse_code'].astype(str).str.strip()
            wh_db['warehouse_name'] = wh_db['warehouse_name'].astype(str).str.upper().str.strip()
            # 注意：Sales 表中左表列名是 'Warehouse' (Code) 和 'Warehouse Name'
            df = df.merge(wh_db, left_on=['Warehouse', 'Warehouse Name'], right_on=['warehouse_code', 'warehouse_name'], how='left')

        # --- QUICK FIX 2: 缺失的仓库 (Warehouse) ---
        missing_wh_sales = df[df['warehouse_type'].isna()].copy()
        if not missing_wh_sales.empty:
            st.warning("⚠️ Mismatch Detected: New Warehouses found in Sales Data.")
            missing_wh_s_df = missing_wh_sales[['Warehouse', 'Warehouse Name']].drop_duplicates()
            missing_wh_s_df = missing_wh_s_df.rename(columns={'Warehouse': 'warehouse_code', 'Warehouse Name': 'warehouse_name'})
            missing_wh_s_df['warehouse_type'] = ALLOWED_WH_TYPES[0] if ALLOWED_WH_TYPES else ""

            edited_wh_s = st.data_editor(
                missing_wh_s_df,
                column_config={"warehouse_type": st.column_config.SelectboxColumn("WH Type", options=ALLOWED_WH_TYPES, required=True)},
                num_rows="dynamic", hide_index=True, key="wh_s_fix_editor"
            )
            if st.button("➕ Quick Add to Warehouse Master (from Sales)"):
                supabase.table("warehouse").insert(edited_wh_s.to_dict(orient='records')).execute()
                st.rerun()
            st.stop()

        # 4. 最终上传（按日期清空重载）
        try:
            # 整理 DataFrame：重命名并删除匹配辅助列
            df = df.rename(columns={'ar_type': 'AR Type', 'warehouse_type': 'Warehouse Type'})
            # 删除多余的 master data 列
            drop_cols = ['ar_code', 'ar_name', 'warehouse_code', 'warehouse_name']
            df = df.drop(columns=[c for c in drop_cols if c in df.columns])
            
            unique_dates = df['Date'].unique().tolist()
            with st.spinner(f"Replacing sales data for: {unique_dates}"):
                supabase.table("sales").delete().in_("Date", unique_dates).execute()
                supabase.table("sales").insert(df.replace({np.nan: None}).to_dict(orient='records')).execute()
            st.success(f"Sales Synced! (Dates updated: {unique_dates})")
            st.rerun()
        except Exception as e:
            st.error(f"Sync failed: {e}")

st.divider()

# --- 4. 资料维护 (Master Data) ---
st.header("2. Master Data Maintenance")
tab_master, tab_settings = st.tabs(["AR & Warehouse List", "⚙️ Type Settings & Protection"])

with tab_master:
    target = st.radio("Select Table:", ["ar", "warehouse"], horizontal=True)
    res = supabase.table(target).select("*").execute()
    df_m = pd.DataFrame(res.data)
    
    if df_m.empty:
        if target == "ar": df_m = pd.DataFrame(columns=["id", "ar_name", "ar_code", "ar_type"])
        else: df_m = pd.DataFrame(columns=["id", "warehouse_name", "warehouse_code", "warehouse_type"])

    # 下拉菜单配置
    config = {
        "ar_type": st.column_config.SelectboxColumn("AR Type", options=ALLOWED_AR_TYPES, required=True),
        "warehouse_type": st.column_config.SelectboxColumn("Warehouse Type", options=ALLOWED_WH_TYPES, required=True)
    }

    edited_m = st.data_editor(df_m, num_rows="dynamic", use_container_width=True, hide_index=True, column_config=config, key=f"ed_{target}")
    
    if st.button(f"Save {target} Records"):
        try:
            supabase.table(target).upsert(edited_m.replace({np.nan: None}).to_dict(orient='records')).execute()
            st.success("Master Table updated!")
            st.rerun()
        except Exception as e:
            st.error(f"Save failed: {e}")

# --- 5. 类型设置与删除保护 (Type Settings with Delete Protection) ---
with tab_settings:
    st.subheader("Manage Dropdown Options")
    st.info("Deleting a type will fail if it's currently used in AR or Warehouse records.")
    
    type_target = st.radio("Select Settings:", ["AR Types", "Warehouse Types"], horizontal=True)
    setting_table = "ar_type_settings" if type_target == "AR Types" else "wh_type_settings"
    main_table = "ar" if type_target == "AR Types" else "warehouse"
    type_col = "ar_type" if type_target == "AR Types" else "warehouse_type"
    
    # 获取当前设置
    raw_types = supabase.table(setting_table).select("*").execute()
    df_types = pd.DataFrame(raw_types.data)
    
    edited_types = st.data_editor(df_types, num_rows="dynamic", use_container_width=True, hide_index=True, key=f"ed_{setting_table}")
    
    if st.button(f"Update {type_target} List"):
        # --- 删除保护逻辑 ---
        # 1. 找出被删掉的行
        original_names = set(df_types['type_name'].tolist())
        current_names = set(edited_types['type_name'].tolist())
        deleted_names = original_names - current_names
        
        if deleted_names:
            # 2. 检查这些被删的 Type 是否正在被业务表使用
            for name in deleted_names:
                usage_check = supabase.table(main_table).select(type_col).eq(type_col, name).limit(1).execute()
                if usage_check.data:
                    st.error(f"❌ DELETE PROTECTION: Cannot delete '{name}'. It is currently assigned to records in the '{main_table}' table.")
                    st.stop() # 终止操作
        
        # 3. 如果通过检查，则执行更新
        try:
            # 对于删除操作，supabase upsert 无法直接同步删除，建议清空再插或使用更复杂逻辑
            # 这里简单处理：全量覆盖逻辑
            # 注意：在生产环境删除通常建议增加 is_active 标记而非物理删除
            supabase.table(setting_table).upsert(edited_types.to_dict(orient='records')).execute()
            st.success(f"{type_target} list updated!")
            st.rerun()
        except Exception as e:
            st.error(f"Update failed: {e}")