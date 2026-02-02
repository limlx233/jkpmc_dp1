import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime

# 数据处理函数封装功能
def generate_description_df():
    data_list = [
                    ['说明',None],
                    ['1.库存调取时间', '2024年12月30日 上午9点','优先级'],
                    ['2.库存组织', 'JKYZ00.健康牙膏智能制造中心   JKCP:健康产品公司   JKRH00.健康日化制造中心','--'],
                    ['3.库存数据来源', '门户系统报表导出','--'],
                    ['4.过期货', '以当前库存物料在库失效日期为准，超过失效日期物料',1],
                    ['5.呆滞品', '≥180天无动销',2],
                    ['6.临期货', '以当前库存成品在库失效日期为准，剩余三分之一效期',3],
                    ['7.预警货', '以当前库存成品在库失效日期为准，剩余三分之二效期',4],
                ]
    current_month_first_day = datetime.now().replace(day=1, hour=8, minute=30, second=0, microsecond=0)
    data_list[1][1] = current_month_first_day.strftime('%Y年%m月%d日 上午%I点%M分')
    df2 = pd.DataFrame(data_list)
    return df2


def read_data(df1, df2):
    cp_warehouses = dict(st.secrets["ccp_warehouse"])
    df2_res = df2[['产品编码', '批次号', '所在仓库']]
    st.dataframe(df2_res)
    df1 = df1[['产品说明', '产品编码', '品规', '库存总件数(销售可用+零货+破损+冻结)', '批次', '失效日期','生产日期', '所在仓库']]
    df1 = df1.rename(columns={'库存总件数(销售可用+零货+破损+冻结)': '库存总件数'})
    df1 = df1.rename(columns={'批次': '批次号'})
    df1['仓库分类'] = df1['所在仓库'].map(cp_warehouses)
    df1['生产日期'] = pd.to_datetime(df1['生产日期'])
    df1['失效日期'] = pd.to_datetime(df1['失效日期'], errors='coerce')
    # 生产日期：失效日期 - 3年 + 1天
    # df1['生产日期'] = df1['失效日期'] - pd.DateOffset(years=3) + pd.Timedelta(days=1)
    # 入库日期等同于生产日期
    df1['入库日期'] = df1['生产日期']
    df1 = df1[df1['仓库分类'].notna()]
    df_res = df1
    return df_res,df2_res


def calculate_expiry(df, date_value):
    df = df.copy()
    df['失效日期'] = pd.to_datetime(df['失效日期'])
    df['生产日期'] = pd.to_datetime(df['生产日期'])
    date_value = pd.to_datetime(date_value)
    df['效期'] = (df['失效日期'] - df['生产日期']).dt.days
    df['剩余效期天数'] = (df['失效日期'] - date_value).dt.days
    df['%(剩余效期/总效期)'] = df['剩余效期天数'] / df['效期']
    df['失效日期'] = df['失效日期'].dt.strftime('%Y-%m-%d')
    df['生产日期'] = df['生产日期'].dt.strftime('%Y-%m-%d')
    return df


def expiry_classification(df):
    df = df.copy()
    conditions = [
        (df['%(剩余效期/总效期)'] <= 0),
        (df['%(剩余效期/总效期)'] <= 1 / 3) & (df['%(剩余效期/总效期)'] > 0),
        (df['%(剩余效期/总效期)'] > 1 / 3) & (df['%(剩余效期/总效期)'] <= 2 / 3),
        (df['%(剩余效期/总效期)'] > 2 / 3)
    ]
    choices = ["过效期", "剩余1/3效期", "剩余2/3效期", ""]
    df['效期类别'] = np.select(conditions, choices, default="")
    return df


def merge_and_mark(df1, df2, key_cols=['产品编码', '批次号', '所在仓库']):
    """
    核心功能：
    1. 精准匹配df1和df2的关键字段交集，标记"≥180天无动销"
    2. 将df2中匹配行的所有列（或指定列）追加到df1中
    3. 非交集行的df2列填充为NaN，不影响df1原有数据
    
    参数：
    - df1: 主数据表（需要标记和追加列的表）
    - df2: 无动销清单表（用于匹配的表）
    - key_cols: 匹配关键字段（默认：产品编码、批次号、所在仓库）
    
    返回：
    - df1_copy: df1的副本，包含新增的"180天无动销"列+df2的所有列
    """
    # ========== 步骤1：数据校验 ==========
    for df, name in [(df1, 'df1'), (df2, 'df2')]:
        missing_cols = [col for col in key_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"{name} 缺少关键字段：{missing_cols}")
    
    # ========== 步骤2：创建副本，保护原数据 ==========
    df1_copy = df1.copy(deep=True)
    df2_copy = df2.copy(deep=True)
    
    # ========== 步骤3：统一关键字段格式（避免类型/空格问题） ==========
    for col in key_cols:
        # 转字符串+去空格+空值统一为NaN
        df1_copy[col] = df1_copy[col].astype(str).str.strip().replace(['nan', ''], np.nan)
        df2_copy[col] = df2_copy[col].astype(str).str.strip().replace(['nan', ''], np.nan)
    
    # ========== 步骤4：处理df2 - 去重+保留所有列（避免一对多匹配） ==========
    # 按关键字段去重，保留第一行（确保每个组合只匹配一次）
    df2_unique = df2_copy.drop_duplicates(subset=key_cols, keep='first')
    
    # ========== 步骤5：左连接匹配 - 同步df2的所有列到df1 ==========
    # 用suffixes避免列名重复（比如df1和df2都有"备注"列时，df2的列会变成"备注_df2"）
    merged_df = df1_copy.merge(
        df2_unique,
        on=key_cols,
        how='left',
        indicator=True,
        suffixes=('', '_df2')
    )
    # ========== 步骤6：标记"≥180天无动销"（仅交集行） ==========
    # 规则：关键字段无空值 + 匹配成功（_merge=both）才标记
    merged_df['180天无动销'] = np.where(
        (merged_df['_merge'] == 'both') & 
        (~merged_df[key_cols].isna().any(axis=1)),
        '≥180天无动销',
        None
    )
    # ========== 步骤7：整理结果 - 移除_merge列，返回最终df1 ==========
    # 移除_merge列（临时标记列）
    result_df = merged_df.drop(columns=['_merge'])
    return result_df


def classify_items(df):
    df = df.copy()
    df['分类'] = ""

    def assign_classification(row):
        classification = []
        if row['效期类别'] == '过效期':
            classification.append('过期货')
        elif row['180天无动销'] == '≥180天无动销':
            classification.append('呆滞品')
        elif row['效期类别'] == '剩余1/3效期' and row['180天无动销']!= '≥180天无动销':
            classification.append('临期货')
        elif row['效期类别'] == '剩余2/3效期' and row['180天无动销']!= '≥180天无动销':
            classification.append('预警货')
        return ', '.join(classification)

    df['分类'] = df.apply(assign_classification, axis=1)
    return df


def filter_and_calculate(df):
    df = df.copy()
    df = df[~(df['分类'] == "")]
    df['处理方案'] = None
    df.loc[:, '数量'] = df['品规'] * df['库存总件数']
    df = df[df['数量'] > 0]
    return df


def reorder_columns(df, columns_to_front):
    df = df.copy()
    all_columns = df.columns.tolist()
    for col in columns_to_front:
        if col not in all_columns:
            raise ValueError(f"列 '{col}' 不在 DataFrame 中")
    new_order = columns_to_front + [col for col in all_columns if col not in columns_to_front]
    df = df[new_order]
    return df


def sort_and_filter(df):
    category_order = ['过期货', '呆滞品', '临期货', '预警货']
    df['分类'] = pd.Categorical(df['分类'], categories=category_order, ordered=True)
    df = df.sort_values(by='分类')
    cols_to_keep = [
        "分类",
        "处理方案",
        "效期类别",
        "180天无动销",
        "%(剩余效期/总效期)",
        "剩余效期天数",
        "产品说明",
        "品规",
        "库存总件数",
        "数量",
        "产品编码",
        "批次号",
        "失效日期",
        "所在仓库",
        "仓库分类"
    ]
    df = df[cols_to_keep]
    df = reorder_columns(df, cols_to_keep)
    return df


def append_sum_row(df):
    summary_row = {
            '产品说明': '合计',
            '库存总件数': df['库存总件数'].sum(),
            '数量': df['数量'].sum()
        }
    res = pd.concat([df, pd.DataFrame([summary_row])], ignore_index=True)
    return res

def filter_special_cases(df):
    """
    根据特定条件筛选 DataFrame
    :param df: 输入的 DataFrame
    :return: 筛选后的多个 DataFrame
    """
    cond1 = df["仓库分类"] == "促销品"
    cond2 = df["仓库分类"] == "非卖品"
    pattern = r'(?<!\d)15g(?!\d)'
    cond3 = df["产品说明"].str.contains(pattern, na=False, regex=True)
    cond4 = df["产品说明"].str.contains("牙膏", na=False)
    cond5 = df["产品说明"].str.contains("达那卡", na=False)
    cond6 = df["产品说明"].str.contains("齿说", na=False)
    cond7 = df['所在仓库'].str.contains('口腔|器械', na=False) # 包含 "口腔" 或 "器械" 的仓库
    cond8 = df['所在仓库'].str.contains('洗护', na=False)
    cond9 = df["仓库分类"] == "正常品种销售"
    df_s11 = append_sum_row(df[(cond9 & cond7) & (~(cond6 |((cond3 & cond4) | cond5) ))]) # df_s11 = append_sum_row(df[cond9 & cond7])
    df_s12 = append_sum_row(df[(cond9 & cond8) & (~(cond6 |((cond3 & cond4) | cond5) ))])
    df_s2 = append_sum_row(df[(df["仓库分类"] == "电商") & (~(cond6 |((cond3 & cond4) | cond5) ))])
    df_s3 = append_sum_row(df[(cond1 | cond2) & (~(cond6 |((cond3 & cond4) | cond5) ))])
    df_s4 = append_sum_row(df[(cond3 & cond4) | cond5]) # 客户拓展部
    df_s5 = append_sum_row(df[cond6]) # 齿说产品

    return df_s11, df_s12, df_s2, df_s3, df_s4, df_s5




# df1, df2_res = read_data(fp1, fp2)
# df1_res = calculate_expiry(df1, date_value)
# df1_res = expiry_classification(df1_res)
# df1_res = merge_and_mark(df1_res, df2_res)
# df1_res = classify_items(df1_res)
# df1_res = filter_and_calculate(df1_res)
# df1_res = sort_and_filter(df1_res)
# df_s11, df_s12, df_s2, df_s3, df_s4, df_s5 = filter_special_cases(df1_res)


