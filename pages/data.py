import streamlit as st
import pandas as pd
import numpy as np
from supabase import create_client

# --- 1. 页面配置 ---
st.set_page_config(page_title="SKG Master Data Management", layout="wide")

# 检查登录状态
if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
    st.warning("Please login on the Home page first.")
    st.stop()

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

# --- 2. 核心数据获取函数 ---

def get_dynamic_options():
    """获取 AR 和 Warehouse 的类型下拉选项"""
    try:
        ar_types = supabase.table("ar_type_settings").select("type_name").execute()
        wh_types = supabase.table("wh_type_settings").select("type_name").execute()
        ar_list = [item['type_name'] for item in ar_types.data]
        wh_list = [item['type_name'] for item in wh_types.data]
        return ar_list, wh_list
    except:
        return [], []

# 获取最新选项
ALLOWED_AR_TYPES, ALLOWED_WH_TYPES = get_dynamic_options()

# --- 3. 界面标题 ---
st.title("⚙️ Master Data Management")
st.markdown("Maintain customer (AR) and warehouse categories to ensure reporting accuracy.")

def handle_quick_add():
    try:
        # 1. 抓取交易数据中缺失类型的组合
        wh_res = supabase.table("stock_details").select('"Warehouse Code", "Warehouse Name"')\
            .is_("warehouse_type", "null").execute()
        
        ar_res = supabase.table("sales_details").select('"AR Code", "AR Name"')\
            .is_("ar_type", "null").execute()

        # 2. 获取 Master 表数据，同时检查是否有 NULL Type
        ex_wh_res = supabase.table("warehouse").select("warehouse_name, warehouse_code, warehouse_type").execute()
        df_ex_wh = pd.DataFrame(ex_wh_res.data)
        
        ex_ar_res = supabase.table("ar").select("ar_name, ar_code, ar_type").execute()
        df_ex_ar = pd.DataFrame(ex_ar_res.data)

        # 记录需要执行的操作状态
        missing_in_master = False # 是否有还没加进 Master 的
        incomplete_in_master = False # Master 里是否有还没填 Type 的

        # --- 处理 Warehouse ---
        to_add_wh = []
        if wh_res.data:
            set_ex_wh = set(zip(df_ex_wh['warehouse_name'], df_ex_wh['warehouse_code'])) if not df_ex_wh.empty else set()
            for _, r in pd.DataFrame(wh_res.data).drop_duplicates().iterrows():
                if (r["Warehouse Name"], r["Warehouse Code"]) not in set_ex_wh:
                    to_add_wh.append({"warehouse_name": r["Warehouse Name"], "warehouse_code": r["Warehouse Code"]})

        # --- 处理 AR ---
        to_add_ar = []
        if ar_res.data:
            set_ex_ar = set(zip(df_ex_ar['ar_name'], df_ex_ar['ar_code'])) if not df_ex_ar.empty else set()
            for _, r in pd.DataFrame(ar_res.data).drop_duplicates().iterrows():
                if (r["AR Name"], r["AR Code"]) not in set_ex_ar:
                    to_add_ar.append({"ar_name": r["AR Name"], "ar_code": r["AR Code"]})

        # --- 检查 Master Table 里的空 Type ---
        # 只要存在没加进去的，或者 Master 里有 NULL 的，都算有 Action
        wh_null_count = df_ex_wh['warehouse_type'].isna().sum() if not df_ex_wh.empty else 0
        ar_null_count = df_ex_ar['ar_type'].isna().sum() if not df_ex_ar.empty else 0

        # 3. 渲染通知
        if to_add_wh:
            st.warning(f"🔎 Found {len(to_add_wh)} new Warehouse combinations not in Master.")
            if st.button("➕ Quick Add New Warehouses"):
                supabase.table("warehouse").upsert(to_add_wh, on_conflict="warehouse_name, warehouse_code").execute()
                st.rerun()
            missing_in_master = True

        if to_add_ar:
            st.warning(f"🔎 Found {len(to_add_ar)} new AR combinations not in Master.")
            if st.button("➕ Quick Add New AR Codes"):
                supabase.table("ar").upsert(to_add_ar, on_conflict="ar_name, ar_code").execute()
                st.rerun()
            missing_in_master = True

        # 如果已经在 Master 里了，但是没填 Type，显示这个更显眼的提示
        if wh_null_count > 0:
            st.error(f"⚠️ {wh_null_count} Warehouses in Master Table are missing 'Warehouse Type'. Please fill them below!")
            incomplete_in_master = True
        
        if ar_null_count > 0:
            st.error(f"⚠️ {ar_null_count} Customers in Master Table are missing 'AR Type'. Please fill them below!")
            incomplete_in_master = True

        # 只有以上两类问题都没有，才显示成功
        if not missing_in_master and not incomplete_in_master:
            st.success("✅ All combinations are correctly mapped and types are assigned.")

    except Exception as e:
        st.error(f"Error: {e}")

handle_quick_add()

# --- 4. 资料维护 (Master Data) ---
tab_master, tab_settings = st.tabs(["📦 AR & Warehouse Master", "🛠️ Type Settings & Protection"])

with tab_master:
    # 1. 选择表
    target = st.pills(
        "Select Table to Manage:", 
        options=["ar", "warehouse"], 
        selection_mode="single",
        default="ar",
        format_func=lambda x: "👤 Customer (AR)" if x=="ar" else "📦 Warehouse List"
    )
    
    if not target:
        target = "ar"

    # 获取对应表数据
    res = supabase.table(target).select("*").order("id", desc=True).execute()
    df_m = pd.DataFrame(res.data)
    
    if df_m.empty:
        if target == "ar": 
            df_m = pd.DataFrame(columns=["id", "ar_name", "ar_code", "ar_type"])
        else: 
            df_m = pd.DataFrame(columns=["id", "warehouse_name", "warehouse_code", "warehouse_type"])

    # 配置编辑器列
    column_config = {
        "id": st.column_config.NumberColumn("ID", help="System ID", disabled=True),
        "ar_type": st.column_config.SelectboxColumn("AR Type", options=ALLOWED_AR_TYPES, required=True),
        "warehouse_type": st.column_config.SelectboxColumn("Warehouse Type", options=ALLOWED_WH_TYPES, required=True),
        "ar_code": st.column_config.TextColumn("AR Code", required=True),
        "warehouse_code": st.column_config.TextColumn("Warehouse Code", required=True),
        "ar_name": st.column_config.TextColumn("AR Name", required=True),
        "warehouse_name": st.column_config.TextColumn("Warehouse Name", required=True)
    }

    st.subheader(f"Editing {target.upper()} Master Data")
    
    # 编辑表格
    edited_m = st.data_editor(
        df_m, 
        num_rows="dynamic", 
        use_container_width=True, 
        hide_index=True, 
        column_config=column_config, 
        key=f"ed_{target}",
        height=800  
    )
    
    if st.button(f"💾 Save {target.upper()} Changes", type="primary"):
        try:
            # --- 核心优化部分 ---
            # 1. 仅将 NaN 转换为 None (这是数据库兼容性必须的，不改变内容)
            # 2. 直接转换为字典列表，不再循环遍历修改任何字符串内容
            data_to_save = edited_m.replace({np.nan: None}).to_dict(orient='records')
            
            # 批量 Upsert 保存原始数据
            supabase.table(target).upsert(data_to_save).execute()
            
            st.success(f"✅ {target.upper()} table updated successfully with original data!")
            st.rerun()
        except Exception as e:
            st.error(f"Save failed: {e}")

# --- 5. 类型设置与删除保护 ---
with tab_settings:
    st.subheader("Dropdown Option Settings")
    st.info("💡 **Tip:** To protect data integrity, you cannot delete a type that is currently assigned to a customer or warehouse.")
    
    col1, col2 = st.columns(2)
    
    # 动态处理两个设置表
    setting_configs = [
        {"label": "AR Types", "table": "ar_type_settings", "main": "ar", "col": "ar_type"},
        {"label": "Warehouse Types", "table": "wh_type_settings", "main": "warehouse", "col": "warehouse_type"}
    ]
    
    for i, cfg in enumerate(setting_configs):
        with col1 if i == 0 else col2:
            st.markdown(f"### {cfg['label']}")
            raw = supabase.table(cfg['table']).select("*").execute()
            df_types = pd.DataFrame(raw.data)
            
            edited_types = st.data_editor(
                df_types, 
                num_rows="dynamic", 
                use_container_width=True, 
                hide_index=True, 
                key=f"ed_{cfg['table']}"
            )
            
            if st.button(f"Update {cfg['label']}"):
                # 删除保护逻辑
                original_names = set(df_types['type_name'].tolist()) if not df_types.empty else set()
                current_names = set(edited_types['type_name'].tolist())
                deleted_names = original_names - current_names
                
                can_proceed = True
                for name in deleted_names:
                    usage_check = supabase.table(cfg['main']).select(cfg['col']).eq(cfg['col'], name).limit(1).execute()
                    if usage_check.data:
                        st.error(f"❌ Cannot delete '{name}': Currently in use.")
                        can_proceed = False
                        break
                
                if can_proceed:
                    try:
                        # 全量覆盖逻辑 (注意：Supabase upsert 不会自动物理删除未包含的行，
                        # 这里如果涉及物理删除，建议先 delete 再 insert，或者增加 is_active 字段)
                        # 为了安全，这里采用 upsert 逻辑
                        supabase.table(cfg['table']).upsert(edited_types.to_dict(orient='records')).execute()
                        st.success(f"{cfg['label']} updated!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update failed: {e}")

st.divider()
st.caption("SKG Data Management System © 2026")