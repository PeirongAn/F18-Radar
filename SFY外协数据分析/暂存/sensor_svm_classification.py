import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.svm import SVC
from sklearn.model_selection import cross_val_score, GridSearchCV, StratifiedKFold
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.preprocessing import StandardScaler
from itertools import combinations
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

def load_sensor_data():
    """从数据库加载传感器任务数据"""
    try:
        # 连接数据库
        conn = sqlite3.connect('valid_data.db')
        
        # 查询传感器任务数据
        query = """
        SELECT data_label, ai_time_ratio, accept_ai_advice, user_id, difficulty, ai_level, audio_enabled, repetition_count,
               ai_control_time, person_control_time, total_time, person_dominance
        FROM trust_data 
        WHERE task_name = 'sensor'
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
        ORDER BY user_id, difficulty, ai_level, audio_enabled, data_label, repetition_count
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            print("没有找到传感器任务的数据")
            return None
        
        print(f"传感器任务原始数据概览:")
        print(f"总记录数: {len(df)}")
        print(f"用户数: {df['user_id'].nunique()}")
        print(f"数据标签数: {df['data_label'].nunique()}")
        
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
        
        # 数据增强：从10个repetition中选择8个的所有组合
        augmented_data = []
        
        # 按用户、实验设置分组（不按data_label分组）
        grouped = df.groupby(['user_id', 'experiment_setting'])
        
        print("开始数据增强（10选8模式）...")
        total_combinations = 0
        
        for (user_id, experiment_setting), group in grouped:
            # 检查是否有10个repetition
            expected_repetitions = 10
            if len(group) != expected_repetitions:
                print(f"警告: {user_id}-{experiment_setting} 只有 {len(group)} 个repetition，跳过")
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
                    'combination_id': f"{user_id}_{experiment_setting}_{combo[0]}{combo[1]}{combo[2]}{combo[3]}{combo[4]}{combo[5]}{combo[6]}{combo[7]}"
                }
                
                augmented_data.append(features)
        
        # 转换为DataFrame
        augmented_df = pd.DataFrame(augmented_data)
        
        print(f"数据增强完成: {len(df)} -> {len(augmented_df)} 样本")
        
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
        
        # 明确显示分类数量
        unique_labels = np.unique(y_data_label)
        print(f"实际类别标签: {unique_labels}")
        print(f"分类数量: {len(unique_labels)} 分类")
        
        return X, y_data_label
        
    except Exception as e:
        print(f"准备增强训练数据错误: {e}")
        return None, None

def hyperparameter_tuning(X, y_data_label):
    """使用网格搜索进行超参数调优"""
    try:
        print(f"\n=== 超参数调优 ===")
        
        # 标准化特征
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # 定义参数网格
        param_grid = {
            'C': [0.001, 0.01, 0.1, 1, 10, 100, 1000],#
            'gamma': [0.001, 0.01, 0.1, 1, 10, 100, 1000],#'scale', 'auto', 
            'kernel': ['rbf'] #, 'linear', 'poly'
        }
        
        # 创建SVM模型
        svm = SVC(random_state=42, probability=True)
        
        # 使用十折交叉验证进行网格搜索
        print("开始网格搜索...")
        # 使用StratifiedKFold确保每折中各类别比例相同
        skfold = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)
        grid_search = GridSearchCV(
            svm, 
            param_grid, 
            cv=skfold, 
            scoring='accuracy',
            n_jobs=-1,  # 使用所有CPU核心
            verbose=1
        )
        
        # 执行网格搜索
        grid_search.fit(X_scaled, y_data_label)
        
        print(f"最佳参数: {grid_search.best_params_}")
        print(f"最佳交叉验证分数: {grid_search.best_score_:.4f}")
        
        return grid_search.best_estimator_, scaler, X_scaled, grid_search.best_params_
        
    except Exception as e:
        print(f"超参数调优错误: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None, None

def train_svm_model_with_cv(X, y_data_label):
    """使用十折交叉验证训练支持向量机模型"""
    try:
        print(f"\n=== 十折交叉验证支持向量机模型训练 ===")
        print(f"样本数: {X.shape[0]}, 特征数: {X.shape[1]}")
        
        # 显示分类信息
        unique_labels = np.unique(y_data_label)
        print(f"SVM分类任务: {len(unique_labels)} 分类")
        print(f"类别标签: {unique_labels}")
        
        # 使用超参数调优
        best_model, scaler, X_scaled, best_params = hyperparameter_tuning(X, y_data_label)
        if best_model is None:
            print("超参数调优失败，使用默认参数")
            best_model = SVC(kernel='rbf', random_state=42, probability=True)
            best_params = {'C': 1.0, 'gamma': 'scale', 'kernel': 'rbf'}
            # 标准化
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
        
        # 使用十折交叉验证 - 与网格搜索使用相同的策略
        skfold = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)
        
        # 计算分类性能指标
        print("计算分类性能指标...")
        cv_accuracy_scores = cross_val_score(best_model, X_scaled, y_data_label, cv=skfold, scoring='accuracy')
        cv_precision_scores = cross_val_score(best_model, X_scaled, y_data_label, cv=skfold, scoring='precision_weighted')
        cv_recall_scores = cross_val_score(best_model, X_scaled, y_data_label, cv=skfold, scoring='recall_weighted')
        cv_f1_scores = cross_val_score(best_model, X_scaled, y_data_label, cv=skfold, scoring='f1_weighted')
        
        print(f"准确率: {cv_accuracy_scores.mean():.4f} ± {cv_accuracy_scores.std():.4f}")
        print(f"精确率: {cv_precision_scores.mean():.4f} ± {cv_precision_scores.std():.4f}")
        print(f"召回率: {cv_recall_scores.mean():.4f} ± {cv_recall_scores.std():.4f}")
        print(f"F1分数: {cv_f1_scores.mean():.4f} ± {cv_f1_scores.std():.4f}")
        
        return {
            'model': best_model,  # 返回最佳参数模型，但不用于性能评估
            'scaler': scaler,
            'best_params': best_params,
            'cv_scores': {
                'accuracy_scores': cv_accuracy_scores,
                'precision_scores': cv_precision_scores,
                'recall_scores': cv_recall_scores,
                'f1_scores': cv_f1_scores,
                'accuracy_mean': cv_accuracy_scores.mean(),
                'accuracy_std': cv_accuracy_scores.std(),
                'precision_mean': cv_precision_scores.mean(),
                'precision_std': cv_precision_scores.std(),
                'recall_mean': cv_recall_scores.mean(),
                'recall_std': cv_recall_scores.std(),
                'f1_mean': cv_f1_scores.mean(),
                'f1_std': cv_f1_scores.std()
            }
        }
        
    except Exception as e:
        print(f"训练模型错误: {e}")
        import traceback
        traceback.print_exc()
        return None

def visualize_results(results):
    """可视化结果"""
    try:
        # 创建图形
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('传感器任务SVM分类结果（十折交叉验证）', fontsize=16)
        
        # 1. 交叉验证准确率分布
        cv_scores = results['cv_scores']
        axes[0, 0].boxplot([cv_scores['accuracy_scores']], labels=['准确率'])
        axes[0, 0].set_title('十折交叉验证准确率分布')
        axes[0, 0].set_ylabel('准确率')
        axes[0, 0].grid(True, alpha=0.3)
        
        # 2. 交叉验证F1分数分布
        axes[0, 1].boxplot([cv_scores['f1_scores']], labels=['F1分数'])
        axes[0, 1].set_title('十折交叉验证F1分数分布')
        axes[0, 1].set_ylabel('F1分数')
        axes[0, 1].grid(True, alpha=0.3)
        
        # 3. 各类别性能指标对比
        metrics = ['准确率', '精确率', '召回率', 'F1分数']
        cv_means = [cv_scores['accuracy_mean'], cv_scores['precision_mean'], 
                   cv_scores['recall_mean'], cv_scores['f1_mean']]
        cv_stds = [cv_scores['accuracy_std'], cv_scores['precision_std'], 
                  cv_scores['recall_std'], cv_scores['f1_std']]
        
        x = np.arange(len(metrics))
        bars = axes[1, 0].bar(x, cv_means, yerr=cv_stds, capsize=5, alpha=0.7, 
                              color=['skyblue', 'lightgreen', 'lightcoral', 'gold'])
        axes[1, 0].set_title('交叉验证性能指标对比')
        axes[1, 0].set_ylabel('分数')
        axes[1, 0].set_xticks(x)
        axes[1, 0].set_xticklabels(metrics, rotation=45)
        axes[1, 0].grid(True, alpha=0.3)
        
        # 在柱状图上添加数值标签
        for i, (mean, std) in enumerate(zip(cv_means, cv_stds)):
            axes[1, 0].text(i, mean + std + 0.01, f'{mean:.3f}', 
                           ha='center', va='bottom', fontsize=10)
        
        # 4. 最佳参数信息
        best_params = results.get('best_params', {})
        param_text = f"最佳超参数:\n\nC = {best_params.get('C', 'N/A')}\n\ngamma = {best_params.get('gamma', 'N/A')}\n\nkernel = {best_params.get('kernel', 'N/A')}\n\n交叉验证结果:\n准确率: {cv_scores['accuracy_mean']:.4f} ± {cv_scores['accuracy_std']:.4f}\nF1分数: {cv_scores['f1_mean']:.4f} ± {cv_scores['f1_std']:.4f}"
        
        axes[1, 1].text(0.05, 0.95, param_text, transform=axes[1, 1].transAxes, 
                       verticalalignment='top', fontsize=10,
                       bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8))
        axes[1, 1].set_title('模型配置与性能')
        axes[1, 1].axis('off')
        
        plt.tight_layout()
        plt.savefig('sensor_svm_cv_results.png', dpi=300, bbox_inches='tight')
        plt.show()
        
    except Exception as e:
        print(f"可视化错误: {e}")

def main():
    """主函数"""
    print("=== 传感器任务支持向量机分类分析（20个特征，十折交叉验证） ===")
    
    # 1. 加载数据
    df = load_sensor_data()
    if df is None:
        return
    
    # 2. 准备训练数据（使用10选8数据增强）
    X, y_data_label = prepare_training_data_with_augmentation(df)
    if X is None:
        return
    
    # 3. 训练SVM模型（使用十折交叉验证和超参数调优）
    results = train_svm_model_with_cv(X, y_data_label)
    if results is None:
        return
    
    # 4. 可视化结果
    visualize_results(results)
    
    # 5. 显示最终结果
    print("\n=== 最终结果（基于十折交叉验证） ===")
    cv_scores = results['cv_scores']
    best_params = results.get('best_params', {})
    
    print(f"最佳超参数: {best_params}")
    print(f"交叉验证准确率: {cv_scores['accuracy_mean']:.4f} ± {cv_scores['accuracy_std']:.4f}")
    print(f"交叉验证精确率: {cv_scores['precision_mean']:.4f} ± {cv_scores['precision_std']:.4f}")
    print(f"交叉验证召回率: {cv_scores['recall_mean']:.4f} ± {cv_scores['recall_std']:.4f}")
    print(f"交叉验证F1分数: {cv_scores['f1_mean']:.4f} ± {cv_scores['f1_std']:.4f}")
    print("\n注意：以上结果基于十折交叉验证，避免了过拟合问题")
    print("分析完成")

if __name__ == "__main__":
    main()
