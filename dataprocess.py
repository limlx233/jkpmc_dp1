# 数据处理函数封装功能
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime


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
    df1 = df1[['产品说明', '产品编码', '品规', '库存总件数 (销售可用+零货+破损+锁定）', '批次', '生产日期', '入库日期', '失效日期', '所在仓库']]
    df1 = df1.rename(columns={'库存总件数 (销售可用+零货+破损+锁定）': '库存总件数'})
    df1 = df1.rename(columns={'批次': '批次号'})
    df1['仓库分类'] = df1['所在仓库'].map(cp_warehouses)
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


def merge_and_mark(df1, df2):
    merged = df1.merge(df2, on=['产品编码', '批次号', '所在仓库'], how='left', indicator=True)
    df1['180天无动销'] = merged['_merge'].apply(lambda x: '≥180天无动销' if x == 'both' else None)
    return df1


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
    cond7 = df['所在仓库'].str.contains('口腔', na=False)
    cond8 = df['所在仓库'].str.contains('洗护', na=False)
    cond9 = df["仓库分类"] == "正常品种销售"
    df_s11 = df[cond9 & cond7]
    df_s12 = df[cond9 & cond8]
    df_s2 = df[df["仓库分类"] == "电商"]
    df_s3 = df[cond1 | cond2]
    df_s4 = df[cond6]
    df_s5 = df[(cond3 & cond4) | cond5]
    return df_s11, df_s12, df_s2, df_s3, df_s4, df_s5





# df1, df2_res = read_data(fp1, fp2)
# df1_res = calculate_expiry(df1, date_value)
# df1_res = expiry_classification(df1_res)
# df1_res = merge_and_mark(df1_res, df2_res)
# df1_res = classify_items(df1_res)
# df1_res = filter_and_calculate(df1_res)
# df1_res = sort_and_filter(df1_res)
# df_s11, df_s12, df_s2, df_s3, df_s4, df_s5 = filter_special_cases(df1_res)


