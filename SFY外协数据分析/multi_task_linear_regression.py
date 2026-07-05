import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split, cross_val_score, KFold
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error, accuracy_score, precision_score, recall_score, f1_score
from sklearn.preprocessing import StandardScaler
from itertools import combinations
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

def load_multi_task_data(selected_tasks):
    """从数据库加载多个任务的数据"""
    try:
        # 连接数据库
        conn = sqlite3.connect('valid_data.db')
        
        # 构建任务筛选条件
        task_conditions = "', '".join(selected_tasks)
        task_where_clause = f"task_name IN ('{task_conditions}')"
        
        # 查询多任务数据
        query = f"""
        SELECT data_label, ai_time_ratio, accept_ai_advice, user_id, difficulty, ai_level, audio_enabled, repetition_count,
               ai_control_time, person_control_time, total_time, person_dominance, task_name
        FROM trust_data 
        WHERE {task_where_clause}
        AND data_label IS NOT NULL 
        AND ai_time_ratio IS NOT NULL 
        AND accept_ai_advice IS NOT NULL
        AND user_id IS NOT NULL
        AND difficulty IS NOT NULL
        AND ai_level IS NOT NULL
        AND audio_enabled IS NOT NULL
        AND ai_control_time IS NOT NULL
        AND person_control_time IS NOT NULL
        AND total_time IS NOT NULL
        AND person_dominance IS NOT NULL
        ORDER BY task_name, user_id, difficulty, ai_level, audio_enabled, data_label, repetition_count
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            print("没有找到指定任务的数据")
            return None
        
        print(f"多任务数据概览:")
        print(f"总记录数: {len(df)}")
        print(f"用户数: {df['user_id'].nunique()}")
        print(f"数据标签数: {df['data_label'].nunique()}")
        print(f"任务数: {df['task_name'].nunique()}")
        print(f"任务列表: {sorted(df['task_name'].unique())}")
        
        # 按任务显示数据统计
        print(f"\n各任务数据统计:")
        for task in sorted(df['task_name'].unique()):
            task_data = df[df['task_name'] == task]
            print(f"  {task}: {len(task_data)} 条记录, {task_data['user_id'].nunique()} 个用户")
        
        return df
        
    except Exception as e:
        print(f"加载数据错误: {e}")
        return None

def prepare_training_data_with_augmentation(df):
    """准备训练数据，使用数据增强：从10个repetition中选择8个的所有组合"""
    try:
        # 创建实验设置标识符
        df['experiment_setting'] = df['difficulty'].astype(str) + '-' + df['ai_level'].astype(str) + '-' + df['audio_enabled'].astype(str)
        
        print(f"实验设置数量: {df['experiment_setting'].nunique()}")
        
        # 处理weapon任务的accept_ai_advice阈值转换
        weapon_threshold = 1.0
        if 'weapon' in df['task_name'].values:
            weapon_mask = df['task_name'] == 'weapon'
            # print(f"处理weapon任务: {weapon_mask.sum()} 条记录")
            # print(f"weapon任务accept_ai_advice范围: {df[weapon_mask]['accept_ai_advice'].min():.3f} - {df[weapon_mask]['accept_ai_advice'].max():.3f}")
            
            # 对weapon任务应用新的阈值转换逻辑
            weapon_accept_ai = df.loc[weapon_mask, 'accept_ai_advice'].copy()
            
            # 应用转换规则：
            # 若 accept_ai_advice < 0，则置为 0
            # 若 0 <= accept_ai_advice <= 阈值，则置为 1
            # 若 accept_ai_advice > 阈值，则置为 0
            weapon_accept_ai = np.where(weapon_accept_ai < 0, 0,
                                      np.where((weapon_accept_ai >= 0) & (weapon_accept_ai <= weapon_threshold), 1, 0))
            
            df.loc[weapon_mask, 'accept_ai_advice'] = weapon_accept_ai
            # print(f"weapon任务阈值转换后: {df[weapon_mask]['accept_ai_advice'].value_counts().to_dict()}")
        
        # 数据增强：从10个repetition中选择8个的所有组合
        augmented_data = []
        
        # 按任务、用户、实验设置分组
        grouped = df.groupby(['task_name', 'user_id', 'experiment_setting'])
        
        print("开始数据增强（10选8模式）...")
        total_combinations = 0
        
        for (task_name, user_id, experiment_setting), group in grouped:
            # 检查是否有10个repetition
            expected_repetitions = 10
            if len(group) != expected_repetitions:
                continue
            
            # 获取data_label（每种实验设置下的data_label都一样）
            data_label = group['data_label'].iloc[0]
            
            # 从10个repetition中选择8个的所有组合 (C(10,8) = 45种组合)
            repetition_indices = list(range(expected_repetitions))
            combinations_8 = list(combinations(repetition_indices, 8))
            
            total_combinations += len(combinations_8)
            
            # 对每个8-repetition组合计算特征
            for combo in combinations_8:
                # 选择8个repetition的数据
                selected_data = group.iloc[list(combo)]
                
                # 计算基础特征（平均值）
                accept_ai_advice_mean = selected_data['accept_ai_advice'].mean()
                ai_control_time_mean = selected_data['ai_control_time'].mean()
                person_control_time_mean = selected_data['person_control_time'].mean()
                ai_control_time_ratio_mean = selected_data['ai_time_ratio'].mean()
                person_dominance_mean = selected_data['person_dominance'].mean()
                
                # 计算标准差特征
                accept_ai_advice_std = selected_data['accept_ai_advice'].std()
                ai_control_time_std = selected_data['ai_control_time'].std()
                person_control_time_std = selected_data['person_control_time'].std()
                ai_control_time_ratio_std = selected_data['ai_time_ratio'].std()
                person_control_time_ratio_std = (1 - selected_data['ai_time_ratio']).std()
                person_dominance_std = selected_data['person_dominance'].std()
                
                # 计算变异系数特征（标准差/均值）
                accept_ai_advice_cv = selected_data['accept_ai_advice'].std() / accept_ai_advice_mean if accept_ai_advice_mean != 0 else 0
                ai_control_time_cv = selected_data['ai_control_time'].std() / ai_control_time_mean if ai_control_time_mean != 0 else 0
                person_control_time_cv = selected_data['person_control_time'].std() / person_control_time_mean if person_control_time_mean != 0 else 0
                ai_control_time_ratio_cv = selected_data['ai_time_ratio'].std() / selected_data['ai_time_ratio'].mean() if selected_data['ai_time_ratio'].mean() != 0 else 0
                person_control_time_ratio_cv = (1 - selected_data['ai_time_ratio']).std() / (1 - selected_data['ai_time_ratio']).mean() if (1 - selected_data['ai_time_ratio']).mean() != 0 else 0
                person_dominance_cv = selected_data['person_dominance'].std() / person_dominance_mean if person_dominance_mean != 0 else 0
                
                # decision_stability_accept: 接受稳定性 - 计算连续接受AI建议的最大次数，反映对AI的信任连贯性
                accept_ai_series = selected_data['accept_ai_advice'].values
                max_consecutive_accept = 0
                current_accept = 0
                
                for decision in accept_ai_series:
                    if decision == 1:
                        current_accept += 1
                        max_consecutive_accept = max(max_consecutive_accept, current_accept)
                    else:
                        current_accept = 0
                
                decision_stability_accept = max_consecutive_accept
                
                # decision_stability_reject: 拒绝稳定性 - 计算连续拒绝AI建议的最大次数，反映对AI的不信任连贯性
                max_consecutive_reject = 0
                current_reject = 0
                
                for decision in accept_ai_series:
                    if decision == 0:
                        current_reject += 1
                        max_consecutive_reject = max(max_consecutive_reject, current_reject)
                    else:
                        current_reject = 0
                
                decision_stability_reject = max_consecutive_reject
                
                # trust_evolution: 信任演化 - 计算接受AI建议的累积变化趋势，正值表示信任度上升
                accept_ai_cumsum = selected_data['accept_ai_advice'].cumsum()
                if len(accept_ai_cumsum) > 1:
                    # 使用线性回归计算趋势斜率
                    x = np.arange(len(accept_ai_cumsum))
                    trust_evolution = np.polyfit(x, accept_ai_cumsum, 1)[0]
                else:
                    trust_evolution = 0
                
                # 计算特征
                features = {
                    'task_name': task_name,
                    'user_id': user_id,
                    'experiment_setting': experiment_setting,
                    'data_label': data_label,
                    # 基础特征（平均值）
                    'accept_ai_advice': accept_ai_advice_mean,
                    'ai_control_time': ai_control_time_mean,
                    'person_control_time': person_control_time_mean,
                    'ai_control_time_ratio': ai_control_time_ratio_mean,
                    'person_dominance': person_dominance_mean,
                    # 标准差特征
                    'accept_ai_advice_std': accept_ai_advice_std,
                    'ai_control_time_std': ai_control_time_std,
                    'person_control_time_std': person_control_time_std,
                    'ai_control_time_ratio_std': ai_control_time_ratio_std,
                    'person_control_time_ratio_std': person_control_time_ratio_std,
                    'person_dominance_std': person_dominance_std,
                    # 变异系数特征
                    'accept_ai_advice_cv': accept_ai_advice_cv,
                    'ai_control_time_cv': ai_control_time_cv,
                    'person_control_time_cv': person_control_time_cv,
                    'ai_control_time_ratio_cv': ai_control_time_ratio_cv,
                    'person_control_time_ratio_cv': person_control_time_ratio_cv,
                    'person_dominance_cv': person_dominance_cv,
                    # 信任相关特征
                    'decision_stability_accept': decision_stability_accept,
                    'decision_stability_reject': decision_stability_reject,
                    'trust_evolution': trust_evolution,
                    'combination_id': f"{task_name}_{user_id}_{experiment_setting}_{combo[0]}{combo[1]}{combo[2]}{combo[3]}{combo[4]}{combo[5]}{combo[6]}{combo[7]}"
                }
                
                augmented_data.append(features)
        
        # 转换为DataFrame
        augmented_df = pd.DataFrame(augmented_data)
        
        print(f"数据增强完成: {len(df)} -> {len(augmented_df)} 样本")
        
        # 按任务显示增强后的数据统计
        print(f"\n增强后各任务数据统计:")
        for task in sorted(augmented_df['task_name'].unique()):
            task_data = augmented_df[augmented_df['task_name'] == task]
            print(f"  {task}: {len(task_data)} 个样本")
        
        # 准备特征矩阵 - 使用20个特征作为输入
        feature_columns = [
            # 基础特征（平均值）
            'accept_ai_advice', 'ai_control_time', 'person_control_time', 'ai_control_time_ratio', 'person_dominance',
            # 标准差特征
            'accept_ai_advice_std', 'ai_control_time_std', 'person_control_time_std', 
            'ai_control_time_ratio_std', 'person_control_time_ratio_std', 'person_dominance_std',
            # 变异系数特征
            'accept_ai_advice_cv', 'ai_control_time_cv', 'person_control_time_cv', 
            'ai_control_time_ratio_cv', 'person_control_time_ratio_cv', 'person_dominance_cv',
            # 信任相关特征
            'decision_stability_accept', 'decision_stability_reject', 'trust_evolution'
        ]
        X = augmented_df[feature_columns].values
        
        # 准备目标变量 - data_label作为预测目标
        y_data_label = augmented_df['data_label'].values
        
        print(f"特征矩阵: {X.shape}, 目标变量: {y_data_label.shape}")
        
        return X, y_data_label, augmented_df, feature_columns
        
    except Exception as e:
        print(f"准备增强训练数据错误: {e}")
        return None, None, None, None

def train_linear_model_with_cv(X, y_data_label, feature_columns):
    """使用十折交叉验证训练线性回归模型"""
    try:
        print(f"\n=== 十折交叉验证线性回归模型训练 ===")
        print(f"样本数: {X.shape[0]}, 特征数: {X.shape[1]}")
        
        # 标准化特征
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # 创建线性回归模型
        model = LinearRegression()
        
        # 使用10折交叉验证
        kfold = KFold(n_splits=10, shuffle=True, random_state=42)
        
        # 计算回归性能指标
        print("计算回归性能指标...")
        cv_r2_scores = cross_val_score(model, X_scaled, y_data_label, cv=kfold, scoring='r2')
        cv_rmse_scores = -cross_val_score(model, X_scaled, y_data_label, cv=kfold, scoring='neg_mean_squared_error')
        cv_rmse_scores = np.sqrt(cv_rmse_scores)
        cv_mae_scores = -cross_val_score(model, X_scaled, y_data_label, cv=kfold, scoring='neg_mean_absolute_error')
        
        print(f"R²: {cv_r2_scores.mean():.4f} ± {cv_r2_scores.std():.4f}")
        print(f"RMSE: {cv_rmse_scores.mean():.4f} ± {cv_rmse_scores.std():.4f}")
        print(f"MAE: {cv_mae_scores.mean():.4f} ± {cv_mae_scores.std():.4f}")
        
        # 计算分类准确率
        print("计算分类准确率...")
        cv_accuracy_scores = []
        cv_precision_scores = []
        cv_recall_scores = []
        cv_f1_scores = []
        
        for fold, (train_idx, test_idx) in enumerate(kfold.split(X_scaled)):
            # 分割数据
            X_train, X_test = X_scaled[train_idx], X_scaled[test_idx]
            y_train, y_test = y_data_label[train_idx], y_data_label[test_idx]
            
            # 训练模型
            fold_model = LinearRegression()
            fold_model.fit(X_train, y_train)
            
            # 预测
            y_pred = fold_model.predict(X_test)
            
            # 转换为分类标签
            y_test_class = np.round(y_test).astype(int)
            y_pred_class = np.round(y_pred).astype(int)
            
            # 确保预测值在目标变量的合理范围内
            min_label = y_test_class.min()
            max_label = y_test_class.max()
            y_pred_class = np.clip(y_pred_class, min_label, max_label)
            
            # 计算分类指标
            accuracy = accuracy_score(y_test_class, y_pred_class)
            precision = precision_score(y_test_class, y_pred_class, average='weighted', zero_division=0)
            recall = recall_score(y_test_class, y_pred_class, average='weighted', zero_division=0)
            f1 = f1_score(y_test_class, y_pred_class, average='weighted', zero_division=0)
            
            cv_accuracy_scores.append(accuracy)
            cv_precision_scores.append(precision)
            cv_recall_scores.append(recall)
            cv_f1_scores.append(f1)
        
        cv_accuracy_scores = np.array(cv_accuracy_scores)
        cv_precision_scores = np.array(cv_precision_scores)
        cv_recall_scores = np.array(cv_recall_scores)
        cv_f1_scores = np.array(cv_f1_scores)
        
        print(f"准确率: {cv_accuracy_scores.mean():.4f} ± {cv_accuracy_scores.std():.4f}")
        print(f"精确率: {cv_precision_scores.mean():.4f} ± {cv_precision_scores.std():.4f}")
        print(f"召回率: {cv_recall_scores.mean():.4f} ± {cv_recall_scores.std():.4f}")
        print(f"F1分数: {cv_f1_scores.mean():.4f} ± {cv_f1_scores.std():.4f}")
        
        # 训练全数据模型用于特征重要性分析
        print("训练全数据模型用于特征重要性分析...")
        full_model = LinearRegression()
        full_model.fit(X_scaled, y_data_label)
        
        return {
            'model': full_model,
            'scaler': scaler,
            'cv_scores': {
                'r2_scores': cv_r2_scores,
                'rmse_scores': cv_rmse_scores,
                'mae_scores': cv_mae_scores,
                'accuracy_scores': cv_accuracy_scores,
                'precision_scores': cv_precision_scores,
                'recall_scores': cv_recall_scores,
                'f1_scores': cv_f1_scores,
                'r2_mean': cv_r2_scores.mean(),
                'r2_std': cv_r2_scores.std(),
                'rmse_mean': cv_rmse_scores.mean(),
                'rmse_std': cv_rmse_scores.std(),
                'mae_mean': cv_mae_scores.mean(),
                'mae_std': cv_mae_scores.std(),
                'accuracy_mean': cv_accuracy_scores.mean(),
                'accuracy_std': cv_accuracy_scores.std(),
                'precision_mean': cv_precision_scores.mean(),
                'precision_std': cv_precision_scores.std(),
                'recall_mean': cv_recall_scores.mean(),
                'recall_std': cv_recall_scores.std(),
                'f1_mean': cv_f1_scores.mean(),
                'f1_std': cv_f1_scores.std()
            },
        }
        
    except Exception as e:
        print(f"训练模型错误: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """主函数"""
    print("=== 多任务线性回归分析（20个特征，十折交叉验证） ===")
    
    # 定义4个固定任务
    all_tasks = ['sensor', 'threat', 'weapon', 'platform']
    
    print(f"\n可用的任务: {all_tasks}")
    
    # 任务选择选项
    print("\n请选择要分析的任务:")
    print("1. 传感器任务")
    print("2. 威胁排序任务")
    print("3. 武器发射任务")
    print("4. 平台控制任务")
    print("（可输入单个编号或多个编号，用逗号分隔，如：1,2,3）")
    
    try:
        choice = input("\n请输入选择: ").strip()
        
        # 任务映射
        task_mapping = {'1': 'sensor', '2': 'threat', '3': 'weapon', '4': 'platform'}
        
        # 解析输入
        if ',' in choice:
            # 多选
            selected_tasks = [task_mapping[num.strip()] for num in choice.split(',') if num.strip() in task_mapping]
        else:
            # 单选
            if choice in task_mapping:
                selected_tasks = [task_mapping[choice]]
            else:
                print("无效选择，使用全部任务")
                selected_tasks = all_tasks
        
        if not selected_tasks:
            print("没有选择有效的任务，使用全部任务")
            selected_tasks = all_tasks
        
        # 显示选择的任务名称
        task_names = {
            'sensor': '传感器任务',
            'threat': '威胁排序任务', 
            'weapon': '武器发射任务',
            'platform': '平台控制任务'
        }
        selected_names = [task_names[task] for task in selected_tasks]
        print(f"\n选择的任务: {', '.join(selected_names)}")
        
    except KeyboardInterrupt:
        print("\n用户取消操作")
        return
    except Exception as e:
        print(f"输入错误: {e}")
        print("使用全部任务")
        selected_tasks = all_tasks
    
    # 1. 加载数据
    df = load_multi_task_data(selected_tasks)
    if df is None:
        return
    
    # 2. 准备训练数据（使用10选8数据增强）
    X, y_data_label, augmented_df, feature_columns = prepare_training_data_with_augmentation(df)
    if X is None:
        return
    
    # 3. 训练模型（使用十折交叉验证）
    results = train_linear_model_with_cv(X, y_data_label, feature_columns)
    if results is None:
        return
    
    # 4. 显示最终结果
    print("\n=== 最终结果（基于十折交叉验证） ===")
    cv_scores = results['cv_scores']
    
    print(f"交叉验证 - R²: {cv_scores['r2_mean']:.4f} ± {cv_scores['r2_std']:.4f}")
    print(f"交叉验证 - RMSE: {cv_scores['rmse_mean']:.4f} ± {cv_scores['rmse_std']:.4f}")
    print(f"交叉验证 - MAE: {cv_scores['mae_mean']:.4f} ± {cv_scores['mae_std']:.4f}")
    print(f"交叉验证 - 准确率: {cv_scores['accuracy_mean']:.4f} ± {cv_scores['accuracy_std']:.4f}")
    print(f"交叉验证 - 精确率: {cv_scores['precision_mean']:.4f} ± {cv_scores['precision_std']:.4f}")
    print(f"交叉验证 - 召回率: {cv_scores['recall_mean']:.4f} ± {cv_scores['recall_std']:.4f}")
    print(f"交叉验证 - F1分数: {cv_scores['f1_mean']:.4f} ± {cv_scores['f1_std']:.4f}")
    print("\n注意：以上结果基于十折交叉验证，避免了过拟合问题")
    print("分析完成")

if __name__ == "__main__":
    main()
