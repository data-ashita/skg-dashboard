import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import timedelta
import numpy as np
from supabase import create_client

# --- 1. 页面配置 ---
st.set_page_config(
    page_title="SKG Meta Ads",
    page_icon="📱",
    layout="wide"
)

# --- 2. 初始化 Supabase 连接 ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

# --- 3. 独立登录检查 ---
# Admin 账号 (DB_USERNAME/DB_PASSWORD) 和 Meta Ads 专属账号 (META_USERNAME/META_PASSWORD)
# 两者皆可登录此页面。此页面的登录状态与主 dashboard.py 独立，互不影响。
def check_password():
    if "meta_password_correct" not in st.session_state:
        st.session_state["meta_password_correct"] = False

    if st.session_state["meta_password_correct"]:
        return True

    with st.container():
        st.subheader("Login / 登入")
        username = st.text_input("Username", key="meta_username_input")
        password = st.text_input("Password", type="password", key="meta_password_input")

        if st.button("Login", type="primary"):
            is_admin = (
                username == st.secrets["DB_USERNAME"]
                and password == st.secrets["DB_PASSWORD"]
            )
            is_meta = (
                username == st.secrets["META_USERNAME"]
                and password == st.secrets["META_PASSWORD"]
            )
            if is_admin or is_meta:
                st.session_state["meta_password_correct"] = True
                st.rerun()
            else:
                st.error("😕 User not found or password incorrect")
                st.session_state["meta_password_correct"] = False

    return False

if not check_password():
    st.stop()

# --- 4. 数据加载 ---
@st.cache_data(ttl=600)
def load_meta_ads_data():
    supabase = init_connection()
    try:
        def load_all_data(table_name, batch_size=1000):
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

        meta_ads_data = load_all_data("meta_ads")
        df_meta_ads_raw = pd.DataFrame(meta_ads_data)

        if not df_meta_ads_raw.empty:
            date_columns = ['reporting_starts', 'reporting_ends', 'starts', 'ends']
            for col in date_columns:
                if col in df_meta_ads_raw.columns:
                    df_meta_ads_raw[col] = pd.to_datetime(df_meta_ads_raw[col], errors='coerce')

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

        return df_meta_ads_raw

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        st.error(f"數據庫連接或查詢失敗: {str(e)}")
        with st.expander("查看詳細錯誤信息"):
            st.code(error_details)
        return pd.DataFrame()

df_meta_ads_raw = load_meta_ads_data()

# --- 5. 主面板 ---
st.title("📱 Meta Ads Performance Analysis")

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
