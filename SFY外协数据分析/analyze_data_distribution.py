"""
分析augmented_data_20250908_191520.db中的数据分布
1. 在各experiment_setting下，分析data_label的分布
2. 对比不同维度下的data_label分布：
   - 动态容限：低容限 vs 高容限
   - 辅助质量与效率：L0 vs L1 vs L2
   - 交互工效：低工效 vs 高工效
"""

import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
def print_distribution_analysis(data1, data2, group1_name, group2_name, test_name):
    """
    打印分布分析结果
    
    参数:
    - data1: 第一组数据
    - data2: 第二组数据
    - group1_name: 第一组名称
    - group2_name: 第二组名称
    - test_name: 测试名称
    """
    trust_labels = {1: '非常不信任', 2: '不信任', 3: '一般', 4: '信任', 5: '非常信任'}
    
    print(f"\n=== {test_name} ===")
    print(f"{group1_name}分布:")
    for label, count in data1.items():
        trust_label = trust_labels.get(label, f'标签{label}')
        print(f"  {trust_label}: {count} ({count/sum(data1)*100:.1f}%)")
    
    print(f"\n{group2_name}分布:")
    for label, count in data2.items():
        trust_label = trust_labels.get(label, f'标签{label}')
        print(f"  {trust_label}: {count} ({count/sum(data2)*100:.1f}%)")

def connect_to_database(db_path):
    """
    连接到数据库
    
    参数:
    - db_path: 数据库文件路径
    
    返回:
    - conn: 数据库连接对象
    """
    try:
        conn = sqlite3.connect(db_path)
        return conn
    except Exception as e:
        print(f"连接数据库失败: {e}")
        return None

def get_table_info(conn):
    """
    获取数据库表信息
    
    参数:
    - conn: 数据库连接对象
    
    返回:
    - tables: 表名列表
    """
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        return tables
    except Exception as e:
        print(f"获取表信息失败: {e}")
        return []

def analyze_label_distribution_by_experiment(conn, table_name):
    """
    分析各experiment_setting下data_label的分布
    
    参数:
    - conn: 数据库连接对象
    - table_name: 表名
    """
    try:
        # 查询数据
        query = f"""
        SELECT experiment_setting, data_label, COUNT(*) as count
        FROM {table_name}
        GROUP BY experiment_setting, data_label
        ORDER BY experiment_setting, data_label
        """
        
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            print(f"表 {table_name} 中没有数据")
            return
        
        # 获取所有experiment_setting和data_label
        experiment_settings = sorted(df['experiment_setting'].unique())
        data_labels = sorted(df['data_label'].unique())
        
        # 创建透视表
        pivot_table = df.pivot(index='experiment_setting', columns='data_label', values='count').fillna(0)
        
        # 计算百分比
        pivot_percent = pivot_table.div(pivot_table.sum(axis=1), axis=0) * 100
        
        # 分析不同维度的分布
        analyze_high_low_distribution(conn, table_name, data_labels)
        analyze_l0_l1_l2_distribution(conn, table_name, data_labels)
        analyze_0_1_distribution(conn, table_name, data_labels)
        
        
        return pivot_table, pivot_percent
        
    except Exception as e:
        print(f"分析label分布时出错: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def analyze_high_low_distribution(conn, table_name, data_labels):
    """
    分析high/low维度的data_label分布 - 汇总统计
    
    参数:
    - conn: 数据库连接对象
    - table_name: 表名
    - data_labels: 数据标签列表
    """
    try:
        # 获取所有包含high和low的experiment_setting
        query = f"""
        SELECT experiment_setting, data_label, COUNT(*) as count
        FROM {table_name}
        WHERE experiment_setting LIKE '%high%' OR experiment_setting LIKE '%low%'
        GROUP BY experiment_setting, data_label
        ORDER BY experiment_setting, data_label
        """
        
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            return
        
        # 分离high和low
        high_settings = df[df['experiment_setting'].str.contains('high', case=False, na=False)]['experiment_setting'].unique()
        low_settings = df[df['experiment_setting'].str.contains('low', case=False, na=False)]['experiment_setting'].unique()
        
        
        # 创建输出目录
        output_dir = f"data_distribution_analysis_{table_name}"
        os.makedirs(output_dir, exist_ok=True)
        
        # 统计high和low设置下的汇总分布
        high_percent = None
        low_percent = None
        
        if len(high_settings) > 0:
            high_data = df[df['experiment_setting'].isin(high_settings)]
            high_summary = high_data.groupby('data_label')['count'].sum()
            high_total = high_summary.sum()
            high_percent = (high_summary / high_total * 100).round(2)
        
        if len(low_settings) > 0:
            low_data = df[df['experiment_setting'].isin(low_settings)]
            low_summary = low_data.groupby('data_label')['count'].sum()
            low_total = low_summary.sum()
            low_percent = (low_summary / low_total * 100).round(2)
        
        # 创建high vs low对比图
        if high_percent is not None and low_percent is not None:
            create_high_low_comparison_plots(high_percent, low_percent, table_name)
            
            # 打印分布分析和显著性检验
            print_distribution_analysis(
                high_summary, low_summary, 
                "低容限", "高容限", 
                "动态容限对比分析"
            )
        
    except Exception as e:
        print(f"分析high/low分布时出错: {e}")

def analyze_l0_l1_l2_distribution(conn, table_name, data_labels):
    """
    分析L0/L1/L2维度的data_label分布 - 汇总统计
    
    参数:
    - conn: 数据库连接对象
    - table_name: 表名
    - data_labels: 数据标签列表
    """
    try:
        # 获取所有包含L0、L1、L2的experiment_setting
        query = f"""
        SELECT experiment_setting, data_label, COUNT(*) as count
        FROM {table_name}
        WHERE experiment_setting LIKE '%L0%' OR experiment_setting LIKE '%L1%' OR experiment_setting LIKE '%L2%'
        GROUP BY experiment_setting, data_label
        ORDER BY experiment_setting, data_label
        """
        
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            return
        
        # 分离L0、L1、L2
        l0_settings = df[df['experiment_setting'].str.contains('L0', case=False, na=False)]['experiment_setting'].unique()
        l1_settings = df[df['experiment_setting'].str.contains('L1', case=False, na=False)]['experiment_setting'].unique()
        l2_settings = df[df['experiment_setting'].str.contains('L2', case=False, na=False)]['experiment_setting'].unique()
        
        
        # 创建输出目录
        output_dir = f"data_distribution_analysis_{table_name}"
        os.makedirs(output_dir, exist_ok=True)
        
        # 统计各L级别的汇总分布
        l_percents = {}
        level_names = {"L0": "L0", "L1": "L1", "L2": "L2"}
        for level, settings in [("L0", l0_settings), ("L1", l1_settings), ("L2", l2_settings)]:
            if len(settings) > 0:
                level_data = df[df['experiment_setting'].isin(settings)]
                level_summary = level_data.groupby('data_label')['count'].sum()
                level_total = level_summary.sum()
                level_percent = (level_summary / level_total * 100).round(2)
                l_percents[level] = level_percent
        
        # 创建L0 vs L1 vs L2对比图
        if len(l_percents) >= 2:
            create_l_level_comparison_plots(l_percents, table_name)
            
            # 打印分布分析
            print(f"\n=== 辅助质量与效率对比分析 ===")
            level_names = {"L0": "L0(低)", "L1": "L1(中)", "L2": "L2(高)"}
            
            # 显示各等级分布
            trust_labels = {1: '非常不信任', 2: '不信任', 3: '一般', 4: '信任', 5: '非常信任'}
            for level, percent_data in l_percents.items():
                data = percent_data * percent_data.sum() / 100  # 转换回原始计数
                print(f"\n{level_names[level]}分布:")
                for label, count in data.items():
                    trust_label = trust_labels.get(label, f'标签{label}')
                    print(f"  {trust_label}: {int(count)} ({count/sum(data)*100:.1f}%)")
        
    except Exception as e:
        print(f"分析L0/L1/L2分布时出错: {e}")

def analyze_0_1_distribution(conn, table_name, data_labels):
    """
    分析0/1维度的data_label分布 - 汇总统计
    
    参数:
    - conn: 数据库连接对象
    - table_name: 表名
    - data_labels: 数据标签列表
    """
    try:
        # 获取所有包含0和1的experiment_setting
        query = f"""
        SELECT experiment_setting, data_label, COUNT(*) as count
        FROM {table_name}
        WHERE experiment_setting LIKE '%0%' OR experiment_setting LIKE '%1%'
        GROUP BY experiment_setting, data_label
        ORDER BY experiment_setting, data_label
        """
        
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            return
        
        # 分离包含0和1的设置
        zero_settings = df[df['experiment_setting'].str.contains(r'\b0\b', regex=True, na=False)]['experiment_setting'].unique()
        one_settings = df[df['experiment_setting'].str.contains(r'\b1\b', regex=True, na=False)]['experiment_setting'].unique()
        
        
        # 创建输出目录
        output_dir = f"data_distribution_analysis_{table_name}"
        os.makedirs(output_dir, exist_ok=True)
        
        # 统计0和1设置下的汇总分布
        zero_percent = None
        one_percent = None
        
        if len(zero_settings) > 0:
            zero_data = df[df['experiment_setting'].isin(zero_settings)]
            zero_summary = zero_data.groupby('data_label')['count'].sum()
            zero_total = zero_summary.sum()
            zero_percent = (zero_summary / zero_total * 100).round(2)
        
        if len(one_settings) > 0:
            one_data = df[df['experiment_setting'].isin(one_settings)]
            one_summary = one_data.groupby('data_label')['count'].sum()
            one_total = one_summary.sum()
            one_percent = (one_summary / one_total * 100).round(2)
        
        # 创建0 vs 1对比图
        if zero_percent is not None and one_percent is not None:
            create_0_1_comparison_plots(zero_percent, one_percent, table_name)
            
            # 打印分布分析和显著性检验
            print_distribution_analysis(
                zero_summary, one_summary, 
                "低工效", "高工效", 
                "交互工效对比分析"
            )
        
    except Exception as e:
        print(f"分析0/1分布时出错: {e}")

def analyze_feature_correlations(conn, table_name):
    """
    分析data_label和各个特征之间的关联关系
    
    参数:
    - conn: 数据库连接对象
    - table_name: 表名
    """
    try:
        # 定义特征类别和特征名
        feature_categories = {
            "基础特征": [
                'accept_ai_advice', 'ai_control_time', 'person_control_time', 
                'ai_control_time_ratio', 'person_dominance'
            ],
            "标准差特征": [
                'accept_ai_advice_std', 'ai_control_time_std', 'person_control_time_std',
                'ai_control_time_ratio_std', 'person_control_time_ratio_std', 'person_dominance_std'
            ],
            "变异系数特征": [
                'accept_ai_advice_cv', 'ai_control_time_cv', 'person_control_time_cv',
                'ai_control_time_ratio_cv', 'person_control_time_ratio_cv', 'person_dominance_cv'
            ],
            "信任演化特征": [
                'decision_stability_accept', 'decision_stability_reject', 'trust_evolution'
            ]
        }
        
        # 查询数据
        query = f"""
        SELECT user_id, data_label, {', '.join([feat for features in feature_categories.values() for feat in features])}
        FROM {table_name}
        WHERE data_label IS NOT NULL
        """
        
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            print(f"表 {table_name} 中没有有效数据")
            return
        
        # 创建输出目录
        output_dir = f"data_distribution_analysis_{table_name}"
        os.makedirs(output_dir, exist_ok=True)
        
        # 设置中文字体和字体大小
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['font.size'] = 20
        plt.rcParams['axes.titlesize'] = 22
        plt.rcParams['axes.labelsize'] = 20
        plt.rcParams['xtick.labelsize'] = 18
        plt.rcParams['ytick.labelsize'] = 18
        
        # 为每个特征类别创建独立的图
        for category_name, features in feature_categories.items():
            # 计算该类别需要的子图数量
            n_features = len(features)
            n_cols = min(2, n_features)  # 每行最多2个子图
            n_rows = (n_features + n_cols - 1) // n_cols  # 计算需要的行数
            
            # 创建该类别的大图，增大子图尺寸
            fig, axes = plt.subplots(n_rows, n_cols, figsize=(10*n_cols, 8*n_rows))
            if n_rows == 1 and n_cols == 1:
                axes = np.array([[axes]])
            elif n_rows == 1:
                axes = axes.reshape(1, -1)
            elif n_cols == 1:
                axes = axes.reshape(-1, 1)
            
            fig.suptitle(f'{category_name} - 信任行为特征统计', fontsize=26, y=0.95)
            
            for idx, feature in enumerate(features):
                row = idx // n_cols
                col = idx % n_cols
                if n_rows == 1 and n_cols == 1:
                    ax = axes[0, 0]
                elif n_rows == 1:
                    ax = axes[0, col]
                elif n_cols == 1:
                    ax = axes[row, 0]
                else:
                    ax = axes[row, col]
                
                # 检查特征是否存在
                if feature not in df.columns:
                    ax.text(0.5, 0.5, f'特征 {feature}\n不存在', ha='center', va='center', transform=ax.transAxes)
                    ax.set_title(f'{feature}', fontsize=12)
                    continue
                
                # 移除缺失值
                feature_data = df[['user_id', 'data_label', feature]].dropna()
                
                if len(feature_data) == 0:
                    ax.text(0.5, 0.5, f'特征 {feature}\n无有效数据', ha='center', va='center', transform=ax.transAxes)
                    ax.set_title(f'{feature}', fontsize=12)
                    continue
                
                # 按信任等级分组绘制小提琴图
                trust_levels = [1, 2, 3, 4, 5]
                violin_data = []
                positions = []
                
                for level in trust_levels:
                    level_data = feature_data[feature_data['data_label'] == level][feature].values
                    if len(level_data) > 0:
                        violin_data.append(level_data)
                        positions.append(level)
                
                if violin_data:
                    # 绘制小提琴图
                    parts = ax.violinplot(violin_data, positions=positions, widths=0.6, showmeans=True, showmedians=True)
                    
                    # 设置小提琴图颜色
                    for pc in parts['bodies']:
                        pc.set_facecolor('lightblue')
                        pc.set_alpha(0.7)
                        pc.set_edgecolor('black')
                        pc.set_linewidth(0.5)
                
                # 打印该特征的分布信息
                print(f"\n--- {category_name} - {feature} ---")
                for level in trust_levels:
                    level_data = feature_data[feature_data['data_label'] == level][feature].values
                    if len(level_data) > 0:
                        trust_label = {1: '非常不信任', 2: '不信任', 3: '一般', 4: '信任', 5: '非常信任'}[level]
                        mean_val = level_data.mean()
                        std_val = level_data.std()
                        min_val = level_data.min()
                        max_val = level_data.max()
                        print(f"  {trust_label}: 均值={mean_val:.3f}, 标准差={std_val:.3f}, 范围=[{min_val:.3f}, {max_val:.3f}], 样本数={len(level_data)}")
                    else:
                        trust_label = {1: '非常不信任', 2: '不信任', 3: '一般', 4: '信任', 5: '非常信任'}[level]
                        print(f"  {trust_label}: 无数据")
                
                # 不打印整体统计信息
                
                # 设置标签
                ax.set_xlabel('信任主观评价结果', fontsize=20)
                ax.set_title(f'{feature}', fontsize=22, pad=8)
                ax.grid(True, alpha=0.3)
                
                # 设置x轴刻度标签
                ax.set_xticks([1, 2, 3, 4, 5])
                ax.set_xticklabels(['非常不信任', '不信任', '一般', '信任', '非常信任'], fontsize=18)
                
                # 小提琴图不需要图例
            
            # 隐藏多余的子图
            for idx in range(len(features), n_rows * n_cols):
                row = idx // n_cols
                col = idx % n_cols
                if n_rows == 1 and n_cols == 1:
                    pass  # 只有一个子图，不需要隐藏
                elif n_rows == 1:
                    axes[0, col].set_visible(False)
                elif n_cols == 1:
                    axes[row, 0].set_visible(False)
                else:
                    axes[row, col].set_visible(False)
            
            plt.tight_layout()
            plt.subplots_adjust(top=0.90, hspace=0.3, wspace=0.2)
            
            # 保存该类别的图
            safe_category_name = category_name.replace('/', '_').replace(' ', '_')
            plt.savefig(f"{output_dir}/{safe_category_name}_distribution_analysis.png", dpi=300, bbox_inches='tight')
            plt.close()
        
        print(f"\n=== 特征分布分析完成 ===")
        print(f"图表已保存到: {output_dir}/")
        for category_name in feature_categories.keys():
            safe_category_name = category_name.replace('/', '_').replace(' ', '_')
            print(f"  - {safe_category_name}_distribution_analysis.png")
        
    except Exception as e:
        print(f"分析特征关联时出错: {e}")
        import traceback
        traceback.print_exc()



def create_high_low_comparison_plots(high_percent, low_percent, table_name):
    """
    创建high vs low设置的对比图表
    
    参数:
    - high_percent: high设置的百分比数据
    - low_percent: low设置的百分比数据
    - table_name: 表名
    """
    try:
        output_dir = f"data_distribution_analysis_{table_name}"
        os.makedirs(output_dir, exist_ok=True)
        
        # 设置中文字体和字体大小
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['font.size'] = 16
        plt.rcParams['axes.titlesize'] = 20
        plt.rcParams['axes.labelsize'] = 18
        plt.rcParams['xtick.labelsize'] = 16
        plt.rcParams['ytick.labelsize'] = 16
        plt.rcParams['legend.fontsize'] = 16
        
        # 创建对比柱状图
        fig, ax = plt.subplots(1, 1, figsize=(12, 8))
        
        # 获取所有data_label
        all_labels = sorted(set(high_percent.index) | set(low_percent.index))
        
        # 准备数据
        high_values = [high_percent.get(label, 0) for label in all_labels]
        low_values = [low_percent.get(label, 0) for label in all_labels]
        
        x = np.arange(len(all_labels))
        width = 0.35
        
        bars1 = ax.bar(x - width/2, high_values, width, label='低容限', alpha=0.8)
        bars2 = ax.bar(x + width/2, low_values, width, label='高容限', alpha=0.8)
        
        ax.set_xlabel('信任主观评价结果', fontsize=18)
        ax.set_ylabel('百分比 (%)', fontsize=18)
        ax.set_title(f'不同动态容限下的信任主观评价结果分布对比', fontsize=20)
        ax.set_xticks(x)
        ax.set_xticklabels(['非常不信任', '不信任', '一般', '信任', '非常信任'])
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 添加数值标签
        for bar in bars1:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                   f'{height:.1f}%', ha='center', va='bottom', fontsize=14)
        
        for bar in bars2:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                   f'{height:.1f}%', ha='center', va='bottom', fontsize=14)
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/high_vs_low_comparison.png", dpi=300, bbox_inches='tight')
        plt.close()
        
    except Exception as e:
        print(f"创建High vs Low对比图表时出错: {e}")
        import traceback
        traceback.print_exc()

def create_l_level_comparison_plots(l_percents, table_name):
    """
    创建L0 vs L1 vs L2设置的对比图表
    
    参数:
    - l_percents: 包含各L级别百分比数据的字典
    - table_name: 表名
    """
    try:
        output_dir = f"data_distribution_analysis_{table_name}"
        os.makedirs(output_dir, exist_ok=True)
        
        # 设置中文字体和字体大小
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['font.size'] = 16
        plt.rcParams['axes.titlesize'] = 20
        plt.rcParams['axes.labelsize'] = 18
        plt.rcParams['xtick.labelsize'] = 16
        plt.rcParams['ytick.labelsize'] = 16
        plt.rcParams['legend.fontsize'] = 16
        
        # 创建对比柱状图
        fig, ax = plt.subplots(1, 1, figsize=(14, 8))
        
        # 获取所有data_label
        all_labels = set()
        for percent_data in l_percents.values():
            all_labels.update(percent_data.index)
        all_labels = sorted(all_labels)
        
        # 准备数据
        x = np.arange(len(all_labels))
        width = 0.25
        
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c']
        for i, (level, percent_data) in enumerate(l_percents.items()):
            values = [percent_data.get(label, 0) for label in all_labels]
            bars = ax.bar(x + i * width, values, width, label=f'{level}等级', 
                         alpha=0.8, color=colors[i % len(colors)])
            
            # 添加数值标签
            for bar in bars:
                height = bar.get_height()
                if height > 0:  # 只在有值的时候显示标签
                    ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                           f'{height:.1f}%', ha='center', va='bottom', fontsize=14)
        
        ax.set_xlabel('信任主观评价结果', fontsize=18)
        ax.set_ylabel('百分比 (%)', fontsize=18)
        ax.set_title(f'不同辅助质量与效率下的信任主观评价结果分布对比', fontsize=20)
        ax.set_xticks(x + width)
        ax.set_xticklabels(['非常不信任', '不信任', '一般', '信任', '非常信任'])
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/l0_vs_l1_vs_l2_comparison.png", dpi=300, bbox_inches='tight')
        plt.close()
        
    except Exception as e:
        print(f"创建L级别对比图表时出错: {e}")
        import traceback
        traceback.print_exc()

def create_0_1_comparison_plots(zero_percent, one_percent, table_name):
    """
    创建0 vs 1设置的对比图表
    
    参数:
    - zero_percent: 包含0设置的百分比数据
    - one_percent: 包含1设置的百分比数据
    - table_name: 表名
    """
    try:
        output_dir = f"data_distribution_analysis_{table_name}"
        os.makedirs(output_dir, exist_ok=True)
        
        # 设置中文字体和字体大小
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['font.size'] = 16
        plt.rcParams['axes.titlesize'] = 20
        plt.rcParams['axes.labelsize'] = 18
        plt.rcParams['xtick.labelsize'] = 16
        plt.rcParams['ytick.labelsize'] = 16
        plt.rcParams['legend.fontsize'] = 16
        
        # 创建对比柱状图
        fig, ax = plt.subplots(1, 1, figsize=(12, 8))
        
        # 获取所有data_label
        all_labels = sorted(set(zero_percent.index) | set(one_percent.index))
        
        # 准备数据
        zero_values = [zero_percent.get(label, 0) for label in all_labels]
        one_values = [one_percent.get(label, 0) for label in all_labels]
        
        x = np.arange(len(all_labels))
        width = 0.35
        
        bars1 = ax.bar(x - width/2, zero_values, width, label='低工效', alpha=0.8)
        bars2 = ax.bar(x + width/2, one_values, width, label='高工效', alpha=0.8)
        
        ax.set_xlabel('信任主观评价结果', fontsize=18)
        ax.set_ylabel('百分比 (%)', fontsize=18)
        ax.set_title(f'不同交互工效下的信任主观评价结果分布对比', fontsize=20)
        ax.set_xticks(x)
        ax.set_xticklabels(['非常不信任', '不信任', '一般', '信任', '非常信任'])
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 添加数值标签
        for bar in bars1:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                   f'{height:.1f}%', ha='center', va='bottom', fontsize=14)
        
        for bar in bars2:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                   f'{height:.1f}%', ha='center', va='bottom', fontsize=14)
        
        plt.tight_layout()
        plt.savefig(f"{output_dir}/zero_vs_one_comparison.png", dpi=300, bbox_inches='tight')
        plt.close()
        
    except Exception as e:
        print(f"创建0 vs 1对比图表时出错: {e}")
        import traceback
        traceback.print_exc()

def main():
    """主函数"""
    db_path = "augmented_data_20250908_191520.db"
    
    print("=== 数据分布分析工具 ===")
    
    # 连接数据库
    conn = connect_to_database(db_path)
    if conn is None:
        return
    
    try:
        # 获取表信息
        tables = get_table_info(conn)
        if not tables:
            print("数据库中没有表")
            return
        
        # 分析每个表
        for table_name in tables:
            print(f"\n分析表: {table_name}")
            
            # 分析各experiment_setting下data_label的分布
            pivot_table, pivot_percent = analyze_label_distribution_by_experiment(conn, table_name)
            
            # 分析特征与data_label的关联关系
            analyze_feature_correlations(conn, table_name)
        
        print("\n=== 分析完成 ===")
        
    except Exception as e:
        print(f"分析过程中出错: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        conn.close()

if __name__ == "__main__":
    main()
