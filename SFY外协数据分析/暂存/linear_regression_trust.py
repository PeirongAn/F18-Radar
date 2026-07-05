import sqlite3
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.feature_selection import mutual_info_regression
from sklearn.metrics import r2_score, accuracy_score, classification_report

from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')



def load_and_prepare_data():
    """加载和准备数据"""
    try:
        conn = sqlite3.connect('valid_data.db')
        
        # 直接读取trust_data表的数据
        print("正在读取valid_data.db中的trust_data表...")
        df = pd.read_sql_query("SELECT * FROM trust_data", conn)
        conn.close()
        print(f"数据加载完成，共 {len(df)} 行，{len(df.columns)} 列")
        return df
        
    except Exception as e:
        print(f"加载数据时出错: {e}")
        return None

def create_sliding_window_features(df, window_length):
    """创建滑动窗口特征"""
    # 复制数据
    df_window = df.copy()
    
    # 确保repetition_count是数值类型
    df_window['repetition_count'] = pd.to_numeric(df_window['repetition_count'], errors='coerce')
    
    # 创建滑动窗口特征
    features = []
    
    for _, group in df_window.groupby(['user_id', 'task_name', 'difficulty', 'ai_level', 'audio_enabled']):
        if len(group) < window_length:
            continue
            
        # 按repetition_count排序
        group = group.sort_values('repetition_count')
        
        # 创建滑动窗口特征
        for i in range(len(group) - window_length + 1):
            window_data = group.iloc[i:i+window_length]
            
            # 基础特征平均值
            ai_time_avg = window_data['ai_time_ratio'].mean()
            accept_ai_avg = window_data['accept_ai_advice'].mean()
            ai_control_time_avg = window_data['ai_control_time'].mean()
            person_control_time_avg = window_data['person_control_time'].mean()
            total_time_avg = window_data['total_time'].mean()
            person_dominance_avg = window_data['person_dominance'].mean()

            # 新增：交互模式特征
            if len(window_data) > 1:
                # AI时间比例的变异系数（标准差/均值）
                ai_time_cv = window_data['ai_time_ratio'].std() / (window_data['ai_time_ratio'].mean() + 1e-8)
                # 接受AI建议的一致性（1-标准差）
                accept_consistency = 1 - window_data['accept_ai_advice'].std()
                # 人员主导程度的稳定性
                dominance_stability = 1 - window_data['person_dominance'].std() / (window_data['person_dominance'].mean() + 1e-8)
            else:
                # 窗长为1时，这些特征无法计算，设为默认值
                ai_time_cv = 0
                accept_consistency = 1
                dominance_stability = 1
            
            # 新增：决策模式特征
            # 连续接受AI建议的次数
            accept_sequence = 0
            for j in range(len(window_data)-1, -1, -1):
                if window_data.iloc[j]['accept_ai_advice'] > 0.5:
                    accept_sequence += 1
                else:
                    break
            
            # 使用窗口中间位置的数据作为目标变量
            target_row = group.iloc[i + window_length // 2]
            
            features.append({
                'user_id': target_row['user_id'],
                'task_name': target_row['task_name'],
                'difficulty': target_row['difficulty'],
                'ai_level': target_row['ai_level'],
                'audio_enabled': target_row['audio_enabled'],
                'repetition_count': target_row['repetition_count'],
                # 基础特征
                'ai_time_ratio_window': ai_time_avg,
                'accept_ai_advice_window': accept_ai_avg,
                'ai_control_time_window': ai_control_time_avg,
                'person_control_time_window': person_control_time_avg,
                'total_time_window': total_time_avg,
                'person_dominance_window': person_dominance_avg,
                # 新增：交互模式特征
                'ai_time_cv': ai_time_cv,
                'accept_consistency': accept_consistency,
                'dominance_stability': dominance_stability,
                # 新增：决策模式特征
                'accept_sequence': accept_sequence,
                'data_label': target_row['data_label']
            })
    
    # 转换为DataFrame
    df_features = pd.DataFrame(features)
    
    return df_features

def calculate_discrete_classification_metrics(y_true, y_pred):
    """计算1-5离散分类的准确率、精确率、召回率、F1分数"""
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
    
    # 将预测值四舍五入到最近的整数，并限制在1-5范围内
    y_pred_rounded = np.round(y_pred).astype(int)
    y_pred_rounded = np.clip(y_pred_rounded, 1, 5)
    
    # 确保真实值也是1-5范围内的整数
    y_true_int = np.round(y_true).astype(int)
    y_true_int = np.clip(y_true_int, 1, 5)
    
    # 计算整体指标
    accuracy = accuracy_score(y_true_int, y_pred_rounded)
    precision_macro = precision_score(y_true_int, y_pred_rounded, average='macro', zero_division=0)
    recall_macro = recall_score(y_true_int, y_pred_rounded, average='macro', zero_division=0)
    f1_macro = f1_score(y_true_int, y_pred_rounded, average='macro', zero_division=0)
    
    # 计算每个类别的指标
    class_metrics = {}
    for class_label in [1, 2, 3, 4, 5]:
        mask = (y_true_int == class_label)
        if np.sum(mask) > 0:
            class_acc = accuracy_score(y_true_int[mask], y_pred_rounded[mask])
            class_precision = precision_score(y_true_int, y_pred_rounded, labels=[class_label], average='micro', zero_division=0)
            class_recall = recall_score(y_true_int, y_pred_rounded, labels=[class_label], average='micro', zero_division=0)
            class_f1 = f1_score(y_true_int, y_pred_rounded, labels=[class_label], average='micro', zero_division=0)
            
            class_metrics[f'类别{class_label}'] = {
                '准确率': class_acc,
                '精确率': class_precision,
                '召回率': class_recall,
                'F1分数': class_f1
            }
        else:
            class_metrics[f'类别{class_label}'] = {
                '准确率': 0.0,
                '精确率': 0.0,
                '召回率': 0.0,
                'F1分数': 0.0
            }
    
    # 计算混淆矩阵
    cm = confusion_matrix(y_true_int, y_pred_rounded, labels=[1, 2, 3, 4, 5])
    
    return {
        'overall_accuracy': accuracy,
        'overall_precision': precision_macro,
        'overall_recall': recall_macro,
        'overall_f1': f1_macro,
        'class_metrics': class_metrics,
        'y_true_class': y_true_int,
        'y_pred_class': y_pred_rounded,
        'confusion_matrix': cm
    }

def build_linear_regression_model_with_window(df, window_length, selected_features=None):
    """构建指定窗长的线性回归模型，可选择使用指定特征或默认特征集"""
    try:
        # 创建滑动窗口特征
        df_features = create_sliding_window_features(df, window_length)
        
        if len(df_features) == 0:
            return None
        
        # 如果没有指定特征，使用默认特征集
        if selected_features is None:
            selected_features = [
                # 基础特征
                'ai_time_ratio_window', 'accept_ai_advice_window', 'ai_control_time_window', 
                'person_control_time_window', 'total_time_window', 'person_dominance_window',
                # 交互模式特征
                'ai_time_cv', 'accept_consistency', 'dominance_stability',
                # 决策模式特征
                'accept_sequence'
            ]
        
        # 检查所有需要的特征是否存在
        missing_features = [f for f in selected_features if f not in df_features.columns]
        if missing_features:
            return None
        
        # 准备特征和目标变量
        X = df_features[selected_features].copy()
        y = df_features['data_label'].copy()
        
        # 转换为数值类型
        for col in X.columns:
            X[col] = pd.to_numeric(X[col], errors='coerce')
        y = pd.to_numeric(y, errors='coerce')
        
        # 删除缺失值
        X = X.dropna()
        y = y[X.index]
        
        if len(X) < 10:  # 样本太少
            return None
        
        # 标准化特征
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        X_scaled = pd.DataFrame(X_scaled, columns=X.columns, index=X.index)
        
        # 分割训练集和测试集
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.1, random_state=42
        )
        
        # 训练线性回归模型
        model = LinearRegression()
        model.fit(X_train, y_train)
        
        # 预测
        y_train_pred = model.predict(X_train)
        y_test_pred = model.predict(X_test)
        
        # 模型评估
        train_r2 = r2_score(y_train, y_train_pred)
        test_r2 = r2_score(y_test, y_test_pred)
        
        # 计算准确率指标
        train_accuracy = calculate_discrete_classification_metrics(y_train, y_train_pred)
        test_accuracy = calculate_discrete_classification_metrics(y_test, y_test_pred)
        
        # 保存模型结果
        results = {
            'window_length': window_length,
            'model_name': '线性回归',
            'model': model,
            'scaler': scaler,
            'feature_names': X.columns.tolist(),
            'coefficients': model.coef_,
            'intercept': model.intercept_,
            'train_r2': train_r2,
            'test_r2': test_r2,
            'train_accuracy': train_accuracy,
            'test_accuracy': test_accuracy,
            'X_train': X_train,
            'X_test': X_test,
            'y_train': y_train,
            'y_test': y_test,
            'y_train_pred': y_train_pred,
            'y_test_pred': y_test_pred
        }
        
        return results
        
    except Exception as e:
        return None



def compare_window_lengths(df):
    """比较不同窗长下的模型性能，每个窗长都进行特征筛选"""
    print("\n=== 比较不同窗长下的模型性能 ===")
    
    window_lengths = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    all_results = []
    
    for window_length in window_lengths:
        # 特征重要性分析
        importance_df = analyze_feature_importance(df, window_length)
        
        if importance_df is not None:
            # 逐步特征选择
            best_features, combinations = stepwise_feature_selection(df, window_length, max_features=10)
            
            if best_features:
                # 使用最佳特征构建模型
                results = build_linear_regression_model_with_window(df, window_length, best_features)
                if results:
                    all_results.append(results)
                    print(f"窗长{window_length}: {len(best_features)}个特征, 准确率{results['test_accuracy']['overall_accuracy']:.4f}")
                else:
                    print(f"窗长{window_length}: 模型构建失败")
            else:
                print(f"窗长{window_length}: 特征选择失败")
        else:
            print(f"窗长{window_length}: 特征分析失败")
    
    # 性能对比
    if all_results:
        print(f"\n=== 所有窗长结果汇总 ===")
        for result in all_results:
            print(f"窗长{result['window_length']}: {len(result['feature_names'])}特征, "
                  f"准确率{result['test_accuracy']['overall_accuracy']:.4f}, "
                  f"精确率{result['test_accuracy']['overall_precision']:.4f}, "
                  f"F1{result['test_accuracy']['overall_f1']:.4f}, "
                  f"R²{result['test_r2']:.4f}")
        
        # 找出最佳模型
        best_result = max(all_results, key=lambda x: x['test_accuracy']['overall_accuracy'])
        
        print(f"\n🏆 整体最优模型:")
        print(f"窗长: {best_result['window_length']}")
        print(f"特征数量: {len(best_result['feature_names'])}")
        print(f"最优特征组合: {', '.join(best_result['feature_names'])}")
        print(f"测试准确率: {best_result['test_accuracy']['overall_accuracy']:.4f}")
        print(f"测试精确率: {best_result['test_accuracy']['overall_precision']:.4f}")
        print(f"测试F1分数: {best_result['test_accuracy']['overall_f1']:.4f}")
        print(f"测试R²: {best_result['test_r2']:.4f}")
        
        return all_results, best_result
    
    return None, None



def analyze_feature_importance(df, window_length=3):
    """分析特征重要性，为逐步筛选提供依据"""
    # 简化输出
    
    # 创建滑动窗口特征
    df_features = create_sliding_window_features(df, window_length)
    
    if len(df_features) == 0:
        return None
    
    # 准备特征和目标变量
    feature_columns = [
        # 基础特征
        'ai_time_ratio_window', 'accept_ai_advice_window', 'ai_control_time_window', 
        'person_control_time_window', 'total_time_window', 'person_dominance_window',
        # 交互模式特征
        'ai_time_cv', 'accept_consistency', 'dominance_stability',
        # 决策模式特征
        'accept_sequence'
    ]
    
    X = df_features[feature_columns].copy()
    y = df_features['data_label'].copy()
    
    # 数据预处理
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors='coerce')
    y = pd.to_numeric(y, errors='coerce')
    
    X = X.dropna()
    y = y[X.index]
    
    if len(X) == 0:
        return None
    
    # 标准化特征
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X_scaled = pd.DataFrame(X_scaled, columns=X.columns, index=X.index)
    
    # 使用线性回归分析特征重要性
    from sklearn.linear_model import LinearRegression
    from sklearn.feature_selection import mutual_info_regression
    
    # 方法1：线性回归系数绝对值
    lr_model = LinearRegression()
    lr_model.fit(X_scaled, y)
    lr_importance = np.abs(lr_model.coef_)
    
    # 方法2：互信息分数
    mi_scores = mutual_info_regression(X_scaled, y, random_state=42)
    
    # 方法3：相关性分析
    correlations = []
    for col in X_scaled.columns:
        corr = np.corrcoef(X_scaled[col], y)[0, 1]
        correlations.append(abs(corr) if not np.isnan(corr) else 0)
    
    # 综合特征重要性评分
    feature_importance_df = pd.DataFrame({
        '特征名': feature_columns,
        '线性回归系数': lr_importance,
        '互信息分数': mi_scores,
        '相关性': correlations
    })
    
    # 计算综合得分（标准化后平均）
    feature_importance_df['线性回归系数_norm'] = feature_importance_df['线性回归系数'] / feature_importance_df['线性回归系数'].max()
    feature_importance_df['互信息分数_norm'] = feature_importance_df['互信息分数'] / feature_importance_df['互信息分数'].max()
    feature_importance_df['相关性_norm'] = feature_importance_df['相关性'] / feature_importance_df['相关性'].max()
    
    feature_importance_df['综合得分'] = (
        feature_importance_df['线性回归系数_norm'] + 
        feature_importance_df['互信息分数_norm'] + 
        feature_importance_df['相关性_norm']
    ) / 3
    
    # 按综合得分排序
    feature_importance_df = feature_importance_df.sort_values('综合得分', ascending=False)
    
    # 简化输出，不显示详细特征重要性
    
    return feature_importance_df

def stepwise_feature_selection(df, window_length=3, max_features=10):
    """逐步特征选择，从最重要的特征开始逐步添加"""
    # 简化输出
    
    # 获取特征重要性
    importance_df = analyze_feature_importance(df, window_length)
    if importance_df is None:
        return None, None
    
    # 按重要性排序的特征列表
    sorted_features = importance_df['特征名'].tolist()
    
    # 逐步添加特征，测试性能
    feature_combinations = []
    best_combination = None
    best_score = -1
    
    for num_features in range(1, min(max_features + 1, len(sorted_features) + 1)):
        # 选择前num_features个最重要的特征
        selected_features = sorted_features[:num_features]
        
        # 测试这个特征组合的性能
        performance = test_feature_combination(df, selected_features, window_length)
        
        if performance:
            feature_combinations.append({
                'num_features': num_features,
                'features': selected_features,
                'test_accuracy': performance['test_accuracy'],
                'test_f1': performance['test_f1'],
                'test_r2': performance['test_r2']
            })
            
            # 记录最佳组合
            current_score = performance['test_accuracy']  # 只按准确率选择
            if current_score > best_score:
                best_score = current_score
                best_combination = selected_features
    
    # 只返回最佳特征组合，不输出详细信息
    
    return best_combination, feature_combinations

def test_feature_combination(df, selected_features, window_length):
    """测试特定特征组合的性能"""
    try:
        # 创建滑动窗口特征
        df_features = create_sliding_window_features(df, window_length)
        
        if len(df_features) == 0:
            return None
        
        # 检查所有需要的特征是否存在
        missing_features = [f for f in selected_features if f not in df_features.columns]
        if missing_features:
            return None
        
        # 准备特征和目标变量
        X = df_features[selected_features].copy()
        y = df_features['data_label'].copy()
        
        # 数据预处理
        for col in X.columns:
            X[col] = pd.to_numeric(X[col], errors='coerce')
        y = pd.to_numeric(y, errors='coerce')
        
        X = X.dropna()
        y = y[X.index]
        
        if len(X) < 10:  # 样本太少
            return None
        
        # 标准化特征
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        X_scaled = pd.DataFrame(X_scaled, columns=X.columns, index=X.index)
        
        # 分割数据
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.1, random_state=42
        )
        
        # 训练模型
        model = LinearRegression()
        model.fit(X_train, y_train)
        
        # 预测和评估
        y_test_pred = model.predict(X_test)
        
        # 计算指标
        test_r2 = r2_score(y_test, y_test_pred)
        test_metrics = calculate_discrete_classification_metrics(y_test, y_test_pred)
        
        return {
            'test_accuracy': test_metrics['overall_accuracy'],
            'test_precision': test_metrics['overall_precision'],
            'test_f1': test_metrics['overall_f1'],
            'test_r2': test_r2
        }
        
    except Exception as e:
        return None



def main():
    """主函数"""
    # 加载数据
    df = load_and_prepare_data()
    
    if df is None:
        print("无法加载数据，程序退出")
        return
    
    print("\n=== 开始多窗长模型分析 ===")
    
    # 进行多窗长分析和特征筛选
    all_results, best_result = compare_window_lengths(df)
    
    if all_results:
        print("\n=== 分析完成 ===")
    else:
        print("分析失败")

if __name__ == "__main__":
    main()
