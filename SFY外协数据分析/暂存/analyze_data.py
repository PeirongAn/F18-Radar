import sqlite3
import pandas as pd
import numpy as np

# 连接数据库
conn = sqlite3.connect('valid_data.db')
df = pd.read_sql_query('SELECT * FROM trust_data', conn)
conn.close()

print('=== 数据基本信息 ===')
print(f'总样本数: {len(df)}')
print(f'列名: {list(df.columns)}')

print('\n=== 目标变量分布 ===')
print(df['data_label'].value_counts().sort_index())

print('\n=== 目标变量统计 ===')
print(f'均值: {df["data_label"].mean():.3f}')
print(f'标准差: {df["data_label"].std():.3f}')
print(f'最小值: {df["data_label"].min()}')
print(f'最大值: {df["data_label"].max()}')

print('\n=== 关键特征统计 ===')
key_features = ['ai_time_ratio', 'accept_ai_advice', 'person_dominance']
for feature in key_features:
    if feature in df.columns:
        print(f'{feature}: 均值={df[feature].mean():.3f}, 标准差={df[feature].std():.3f}')

print('\n=== 滑动窗口特征分析 ===')
# 模拟创建滑动窗口特征
from linear_regression_trust import create_sliding_window_features
df_window = create_sliding_window_features(df, 3)
print(f'窗长3的样本数: {len(df_window)}')
if len(df_window) > 0:
    print(f'目标变量分布: {df_window["data_label"].value_counts().sort_index()}')
    print(f'目标变量均值: {df_window["data_label"].mean():.3f}')

