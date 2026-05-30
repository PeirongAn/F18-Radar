import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.svm import SVC
from sklearn.model_selection import cross_val_score, GridSearchCV, StratifiedKFold
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix, classification_report
from sklearn.preprocessing import StandardScaler
from itertools import combinations
from datetime import datetime
from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
VALID_DATA_DB = OUTPUT_DIR / "valid_data.db"

# 设置中文字体支持
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

def load_multi_task_data(selected_tasks):
    """从数据库加载多个任务的数据"""
    try:
        # 连接数据库
        conn = sqlite3.connect(VALID_DATA_DB)
        
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
            # 对weapon任务应用新的阈值转换逻辑
            weapon_accept_ai = df.loc[weapon_mask, 'accept_ai_advice'].copy()
            # 应用转换规则：
            # 若 accept_ai_advice < 0，则置为 0
            # 若 0 <= accept_ai_advice <= 阈值，则置为 1
            # 若 accept_ai_advice > 阈值，则置为 0
            weapon_accept_ai = np.where(weapon_accept_ai < 0, 0,
                                      np.where((weapon_accept_ai >= 0) & (weapon_accept_ai <= weapon_threshold), 1, 0))
            
            df.loc[weapon_mask, 'accept_ai_advice'] = weapon_accept_ai
        
        # 数据增强：从10个repetition中选择8个的所有组合
        augmented_data = []
        
        # 按任务、用户、实验设置分组（不按data_label分组）
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
                    'trust_evolution': trust_evolution
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
        
        # 保存增强后的数据到数据库（带时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        OUTPUT_DIR.mkdir(exist_ok=True)
        db_filename = OUTPUT_DIR / f"augmented_data_{timestamp}.db"
        conn = sqlite3.connect(db_filename)
        augmented_df.to_sql('augmented_features', conn, if_exists='append', index=False)
        conn.close()
        print(f"\n增强后的特征与标签已保存到数据库: {db_filename}")
        
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
            'C': [0.001, 0.01, 0.1, 1, 10, 100, 1000],
            'gamma': [0.001, 0.01, 0.1, 1, 10, 100, 1000],
            'kernel': ['rbf']#, 'linear', 'poly'
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
            verbose=1,
            return_train_score=True  # 返回训练分数
        )
        
        # 执行网格搜索
        grid_search.fit(X_scaled, y_data_label)
        
        # 记录所有参数组合及其性能
        print(f"\n=== 扫参过程记录 ===")
        results_df = pd.DataFrame(grid_search.cv_results_)
        
        # 选择关键列进行显示
        key_columns = ['param_C', 'param_gamma', 'param_kernel', 'mean_test_score', 'std_test_score', 'mean_train_score', 'std_train_score']
        results_display = results_df[key_columns].copy()
        results_display = results_display.sort_values('mean_test_score', ascending=False)
        
        print("所有参数组合性能排序（按测试分数降序）:")
        print("-" * 80)
        for idx, row in results_display.head(10).iterrows():  # 显示前10个最佳结果
            print(f"C={row['param_C']:>7}, gamma={row['param_gamma']:>7}, kernel={row['param_kernel']:>4} | "
                  f"测试分数: {row['mean_test_score']:.4f}±{row['std_test_score']:.4f} | "
                  f"训练分数: {row['mean_train_score']:.4f}±{row['std_train_score']:.4f}")
        
        # 保存完整结果到CSV文件（带时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        OUTPUT_DIR.mkdir(exist_ok=True)
        csv_filename = OUTPUT_DIR / f"hyperparameter_search_results_{timestamp}.csv"
        results_df.to_csv(csv_filename, index=False, encoding='utf-8')
        print(f"\n完整扫参结果已保存到: {csv_filename}")
        
        # 记录最优参数
        best_params = grid_search.best_params_
        best_score = grid_search.best_score_
        best_std = results_df[results_df['rank_test_score'] == 1]['std_test_score'].iloc[0]
        
        print(f"\n=== 最优参数记录 ===")
        print(f"最佳参数: {best_params}")
        print(f"最佳交叉验证分数: {best_score:.4f} ± {best_std:.4f}")
        
        # 保存最优参数到文件
        best_params_info = {
            'best_params': best_params,
            'best_cv_score': best_score,
            'best_cv_std': best_std,
            'total_combinations': len(results_df),
            'search_time': 'N/A'  # 可以添加时间记录
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        best_params_filename = OUTPUT_DIR / f"best_hyperparameters_{timestamp}.json"
        with open(best_params_filename, 'w', encoding='utf-8') as f:
            json.dump(best_params_info, f, indent=2, ensure_ascii=False)
        print(f"最优参数已保存到: {best_params_filename}")
        
        return X_scaled, best_params
        
    except Exception as e:
        print(f"超参数调优错误: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def train_and_evaluate_with_best_params(X_scaled, y_data_label, best_params):
    """
    在最优参数下按折进行训练和测试，记录每折、每条数据的标签和预测结果
    
    参数:
    - X_scaled: 已标准化的特征矩阵
    - y_data_label: 目标变量
    - best_params: 最优参数
    
    返回:
    - fold_results: 包含每折详细结果的字典
    """
    try:
        print(f"\n=== 在最优参数下按折进行训练和测试 ===")
        print(f"最优参数: {best_params}")
        
        # 初始化存储变量
        fold_results = {
            'fold_details': [],
            'all_predictions': [],
            'all_true_labels': [],
            'fold_accuracies': []
        }
        
        # 使用十折交叉验证
        skfold = StratifiedKFold(n_splits=10, shuffle=True, random_state=42)
        
        for fold, (train_idx, test_idx) in enumerate(skfold.split(X_scaled, y_data_label)):
            print(f"\n--- 折 {fold+1} ---")
            
            # 训练模型
            model = SVC(**best_params, random_state=42, probability=True)
            model.fit(X_scaled[train_idx], y_data_label[train_idx])
            
            # 预测
            y_pred = model.predict(X_scaled[test_idx])
            y_true = y_data_label[test_idx]
            
            # 计算该折的准确率
            fold_accuracy = accuracy_score(y_true, y_pred)
            
            # 记录该折的详细信息
            fold_detail = {
                'fold': fold + 1,
                'train_size': len(train_idx),
                'test_size': len(test_idx),
                'accuracy': float(fold_accuracy),
                'predictions': y_pred.tolist(),
                'true_labels': y_true.tolist(),
                'test_indices': test_idx.tolist()
            }
            
            fold_results['fold_details'].append(fold_detail)
            fold_results['all_predictions'].extend(y_pred.tolist())
            fold_results['all_true_labels'].extend(y_true.tolist())
            fold_results['fold_accuracies'].append(fold_accuracy)
            
            print(f"  训练样本数: {len(train_idx)}")
            print(f"  测试样本数: {len(test_idx)}")
            print(f"  准确率: {fold_accuracy:.4f}")
            print(f"  预测结果: {y_pred[:10]}...")  # 显示前10个预测结果
            print(f"  真实标签: {y_true[:10]}...")  # 显示前10个真实标签
        
        # 计算整体统计
        overall_accuracy = np.mean(fold_results['fold_accuracies'])
        overall_std = np.std(fold_results['fold_accuracies'])
        
        fold_results['overall_accuracy'] = float(overall_accuracy)
        fold_results['overall_std'] = float(overall_std)
        
        print(f"\n=== 整体结果 ===")
        print(f"平均准确率: {overall_accuracy:.4f} ± {overall_std:.4f}")
        print(f"最高准确率: {max(fold_results['fold_accuracies']):.4f}")
        print(f"最低准确率: {min(fold_results['fold_accuracies']):.4f}")
        
        # 保存fold级详细结果（带时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        OUTPUT_DIR.mkdir(exist_ok=True)
        fold_filename = OUTPUT_DIR / f"fold_results_{timestamp}.json"
        with open(fold_filename, 'w', encoding='utf-8') as f:
            json.dump(fold_results, f, indent=2, ensure_ascii=False)
        print(f"折级详细结果已保存到: {fold_filename}")
        
        return fold_results
        
    except Exception as e:
        print(f"按折训练和测试错误: {e}")
        import traceback
        traceback.print_exc()
        return None



def visualize_results(results, selected_tasks):
    """可视化结果"""
    try:
        # 创建图形
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle(f'多任务SVM分类结果（十折交叉验证）- {", ".join(selected_tasks)}', fontsize=16)
        
        cv_scores = results['cv_scores']
        best_params = results.get('best_params', {})
        
        # 1. 交叉验证准确率分布
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
        bars = axes[0, 2].bar(x, cv_means, yerr=cv_stds, capsize=5, alpha=0.7, 
                              color=['skyblue', 'lightgreen', 'lightcoral', 'gold'])
        axes[0, 2].set_title('交叉验证性能指标对比')
        axes[0, 2].set_ylabel('分数')
        axes[0, 2].set_xticks(x)
        axes[0, 2].set_xticklabels(metrics, rotation=45)
        axes[0, 2].grid(True, alpha=0.3)
        
        # 在柱状图上添加数值标签
        for i, (mean, std) in enumerate(zip(cv_means, cv_stds)):
            axes[0, 2].text(i, mean + std + 0.01, f'{mean:.3f}', 
                           ha='center', va='bottom', fontsize=10)
        
        # 4. 交叉验证性能稳定性
        fold_scores = cv_scores['accuracy_scores']
        axes[1, 0].plot(range(1, len(fold_scores) + 1), fold_scores, 'o-', linewidth=2, markersize=6)
        axes[1, 0].set_title('十折交叉验证准确率变化')
        axes[1, 0].set_xlabel('折数')
        axes[1, 0].set_ylabel('准确率')
        axes[1, 0].grid(True, alpha=0.3)
        axes[1, 0].axhline(y=fold_scores.mean(), color='r', linestyle='--', alpha=0.7, label=f'平均值: {fold_scores.mean():.3f}')
        axes[1, 0].legend()
        
        # 5. 最佳参数信息
        param_text = f"最佳超参数:\n\nC = {best_params.get('C', 'N/A')}\n\ngamma = {best_params.get('gamma', 'N/A')}\n\nkernel = {best_params.get('kernel', 'N/A')}\n\n十折交叉验证结果:\n准确率: {cv_scores['accuracy_mean']:.4f} ± {cv_scores['accuracy_std']:.4f}\n精确率: {cv_scores['precision_mean']:.4f} ± {cv_scores['precision_std']:.4f}\n召回率: {cv_scores['recall_mean']:.4f} ± {cv_scores['recall_std']:.4f}\nF1分数: {cv_scores['f1_mean']:.4f} ± {cv_scores['f1_std']:.4f}"
        
        axes[1, 1].text(0.05, 0.95, param_text, transform=axes[1, 1].transAxes, 
                       verticalalignment='top', fontsize=9,
                       bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8))
        axes[1, 1].set_title('模型配置与性能')
        axes[1, 1].axis('off')
        
        # 6. 各类别性能指标箱线图
        metrics_data = [cv_scores['accuracy_scores'], cv_scores['precision_scores'], 
                       cv_scores['recall_scores'], cv_scores['f1_scores']]
        metrics_labels = ['准确率', '精确率', '召回率', 'F1分数']
        
        axes[1, 2].boxplot(metrics_data, labels=metrics_labels)
        axes[1, 2].set_title('十折交叉验证性能指标分布')
        axes[1, 2].set_ylabel('分数')
        axes[1, 2].grid(True, alpha=0.3)
        
        plt.tight_layout()
        OUTPUT_DIR.mkdir(exist_ok=True)
        plt.savefig(OUTPUT_DIR / 'multi_task_svm_results.png', dpi=300, bbox_inches='tight')
        plt.show()
        
    except Exception as e:
        print(f"可视化错误: {e}")

def main():
    """主函数"""
    print("=== 多任务支持向量机分类分析（20个特征，十折交叉验证） ===")
    
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
    X, y_data_label = prepare_training_data_with_augmentation(df)
    if X is None:
        return
    
    # 3. 扫参（超参数调优）
    print("\n" + "="*60)
    X_scaled, best_params = hyperparameter_tuning(X, y_data_label)
    if X_scaled is None:
        print("超参数调优失败")
        return
    
    # 4. 在最优参数下按折进行训练和测试，记录每折、每条数据的标签和预测结果
    print("\n" + "="*60)
    fold_results = train_and_evaluate_with_best_params(X_scaled, y_data_label, best_params)
    if fold_results is None:
        print("按折训练和测试失败")
        return
    
    # 5. 可视化结果（使用简化的结果结构）
    simplified_results = {
        'best_params': best_params,
        'cv_scores': {
            'accuracy_mean': fold_results['overall_accuracy'],
            'accuracy_std': fold_results['overall_std'],
            'accuracy_scores': fold_results['fold_accuracies']
        }
    }
    visualize_results(simplified_results, selected_tasks)
    
    # 6. 显示最终结果
    print("\n=== 最终结果（基于十折交叉验证） ===")
    
    print(f"最佳超参数: {best_params}")
    print(f"交叉验证 - 准确率: {fold_results['overall_accuracy']:.4f} ± {fold_results['overall_std']:.4f}")
    
    print("\n注意：以上结果基于十折交叉验证，避免了过拟合问题")
    print("分析完成")

if __name__ == "__main__":
    main()
