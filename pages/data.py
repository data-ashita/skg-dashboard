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

# 获取当前选项
ALLOWED_AR_TYPES, ALLOWED_WH_TYPES = get_dynamic_options()

st.title("📤 Data Management Center")

# --- 3. 业务数据同步 (Transactional Data) ---
st.header("1. Sync Transactional Data")

stock_excel_cols = ["Stock Code", "Stock Name", "Warehouse Code", "Warehouse Name", "Quantity"]
sales_excel_cols = ["CoID", "Invoice Number", "Stock Code", "Stock Name", "Quantity", "Unit Price", "Sales", "Date", "Warehouse", "Warehouse Name", "AR Code", "AR Name"]

col1, col2 = st.columns(2)

with col1:
    st.subheader("Sync Stock Table")
    st.download_button("📥 Stock Template", generate_template(stock_excel_cols), "stock_template.xlsx")
    f_stock = st.file_uploader("Upload Stock Excel", type=['xlsx'], key="up_stock")
    
    if f_stock and st.button("Sync Stock"):
        df = pd.read_excel(f_stock)
        df.columns = df.columns.str.strip()
        
        # 匹配仓库类型 (双重匹配 Code + Name)
        wh_ref = supabase.table("warehouse").select("warehouse_code, warehouse_name, warehouse_type").execute()
        if wh_ref.data:
            df_wh = pd.DataFrame(wh_ref.data)
            df = df.merge(df_wh, left_on=['Warehouse Code', 'Warehouse Name'], right_on=['warehouse_code', 'warehouse_name'], how='left')
            
            if not df[df['warehouse_type'].isna()].empty:
                st.error("❌ ERROR: Warehouse Code/Name mismatch found in some rows!")
                st.write(df[df['warehouse_type'].isna()][['Warehouse Code', 'Warehouse Name']])
                st.stop()
            
            df = df.rename(columns={'warehouse_type': 'Warehouse Type'}).drop(columns=['warehouse_code', 'warehouse_name'])
        
        df = df.replace({np.nan: None})
        try:
            supabase.table("stock").upsert(df.to_dict(orient='records')).execute()
            st.success("Stock synced successfully!")
        except Exception as e:
            st.error(f"Sync failed: {e}")

with col2:
    st.subheader("Sync Sales Table")
    st.download_button("📥 Sales Template", generate_template(sales_excel_cols), "sales_template.xlsx")
    f_sales = st.file_uploader("Upload Sales Excel", type=['xlsx'], key="up_sales")
    
    if f_sales and st.button("Sync Sales"):
        df = pd.read_excel(f_sales)
        df.columns = df.columns.str.strip()
        
        # 1. 匹配 AR (Code + Name)
        ar_db = pd.DataFrame(supabase.table("ar").select("ar_code, ar_name, ar_type").execute().data)
        df = df.merge(ar_db, left_on=['AR Code', 'AR Name'], right_on=['ar_code', 'ar_name'], how='left')
        if not df[df['ar_type'].isna()].empty:
            st.error("❌ ERROR: AR Code/Name mismatch!")
            st.write(df[df['ar_type'].isna()][['AR Code', 'AR Name']])
            st.stop()
        
        # 2. 匹配 Warehouse (Code + Name)
        wh_db = pd.DataFrame(supabase.table("warehouse").select("warehouse_code, warehouse_name, warehouse_type").execute().data)
        df = df.merge(wh_db, left_on=['Warehouse', 'Warehouse Name'], right_on=['warehouse_code', 'warehouse_name'], how='left')
        if not df[df['warehouse_type'].isna()].empty:
            st.error("❌ ERROR: Warehouse mismatch!")
            st.write(df[df['warehouse_type'].isna()][['Warehouse', 'Warehouse Name']])
            st.stop()
            
        df = df.rename(columns={'ar_type': 'AR Type', 'warehouse_type': 'Warehouse Type'})
        df = df.drop(columns=['ar_code', 'ar_name', 'warehouse_code', 'warehouse_name'])
        
        if 'Date' in df.columns: df['Date'] = df['Date'].astype(str)
        df = df.replace({np.nan: None})
        try:
            supabase.table("sales").upsert(df.to_dict(orient='records')).execute()
            st.success("Sales synced successfully!")
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