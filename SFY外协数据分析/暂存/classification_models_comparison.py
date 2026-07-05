import sqlite3
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, precision_score, recall_score, f1_score
from imblearn.over_sampling import SMOTE
import warnings
warnings.filterwarnings('ignore')

def load_data():
    """加载数据"""
    try:
        conn = sqlite3.connect('valid_data.db')
        df = pd.read_sql_query("SELECT * FROM trust_data", conn)
        conn.close()
        print(f"数据加载完成，共 {len(df)} 行，{len(df.columns)} 列")
        return df
    except Exception as e:
        print(f"加载数据时出错: {e}")
        return None

def prepare_features_and_target(df):
    """准备特征和目标变量"""
    # 选择指定的特征列
    feature_columns = [
        'ai_control_time', 
        'person_control_time', 
        'total_time', 
        'ai_time_ratio', 
        'person_dominance', 
        'accept_ai_advice'
    ]
    
    # 检查特征列是否存在
    missing_features = [col for col in feature_columns if col not in df.columns]
    if missing_features:
        print(f"缺少特征列: {missing_features}")
        return None, None
    
    # 准备特征和目标变量
    X = df[feature_columns].copy()
    y = df['data_label'].copy()
    
    print(f"特征数据形状: {X.shape}")
    print(f"目标变量分布:")
    print(y.value_counts().sort_index())
    
    # 数据预处理
    print("\n=== 数据预处理 ===")
    print(f"预处理前缺失值: X={X.isnull().sum().sum()}, y={y.isnull().sum()}")
    
    # 转换为数值类型
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors='coerce')
    y = pd.to_numeric(y, errors='coerce')
    
    # 删除缺失值
    X = X.dropna()
    y = y[X.index]
    
    print(f"删除缺失值后: X={X.shape}, y={len(y)}")
    print(f"最终缺失值: X={X.isnull().sum().sum()}, y={y.isnull().sum()}")
    
    return X, y

def train_and_evaluate_models(X, y):
    """训练和评估多种分类模型"""
    print("\n=== 数据分割 ===")
    # 分割数据
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )
    
    print(f"训练集大小: {X_train.shape[0]}")
    print(f"测试集大小: {X_test.shape[0]}")
    
    # 标准化特征
    print("\n=== 特征标准化 ===")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # 处理类别不平衡
    print("\n=== 处理类别不平衡 ===")
    smote = SMOTE(random_state=42)
    X_train_balanced, y_train_balanced = smote.fit_resample(X_train_scaled, y_train)
    
    print(f"平衡后训练集大小: {X_train_balanced.shape[0]}")
    print(f"平衡后目标变量分布: {np.bincount(y_train_balanced.astype(int))}")
    
    # 定义模型
    models = {
        '随机森林': RandomForestClassifier(
            n_estimators=100, 
            random_state=42, 
            class_weight='balanced',
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2
        ),
        '支持向量机': SVC(
            random_state=42, 
            class_weight='balanced',
            kernel='rbf',
            C=1.0,
            gamma='scale',
            probability=True
        ),
        '逻辑回归': LogisticRegression(
            random_state=42, 
            class_weight='balanced', 
            max_iter=1000,
            multi_class='ovr'
        )
    }
    
    results = {}
    
    print("\n=== 模型训练和评估 ===")
    for name, model in models.items():
        print(f"\n--- 训练 {name} ---")
        try:
            # 训练模型
            model.fit(X_train_balanced, y_train_balanced)
            
            # 预测
            y_pred = model.predict(X_test_scaled)
            y_pred_proba = model.predict_proba(X_test_scaled) if hasattr(model, 'predict_proba') else None
            
            # 计算评估指标
            accuracy = accuracy_score(y_test, y_pred)
            precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
            recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
            f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
            
            # 交叉验证
            cv_scores = cross_val_score(
                model, X_train_balanced, y_train_balanced, 
                cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=42),
                scoring='accuracy'
            )
            
            # 保存结果
            results[name] = {
                'model': model,
                'accuracy': accuracy,
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'cv_mean': cv_scores.mean(),
                'cv_std': cv_scores.std(),
                'y_test': y_test,
                'y_pred': y_pred,
                'y_pred_proba': y_pred_proba,
                'classification_report': classification_report(y_test, y_pred),
                'confusion_matrix': confusion_matrix(y_test, y_pred)
            }
            
            print(f"准确率: {accuracy:.4f}")
            print(f"精确率: {precision:.4f}")
            print(f"召回率: {recall:.4f}")
            print(f"F1分数: {f1:.4f}")
            print(f"交叉验证: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
            
        except Exception as e:
            print(f"{name} 训练失败: {e}")
            results[name] = None
    
    return results, scaler, X.columns.tolist()

def print_detailed_results(results):
    """打印详细的模型结果"""
    print("\n" + "="*80)
    print("详细模型性能对比")
    print("="*80)
    
    # 创建结果对比表
    comparison_data = []
    for name, result in results.items():
        if result is not None:
            comparison_data.append({
                '模型': name,
                '准确率': f"{result['accuracy']:.4f}",
                '精确率': f"{result['precision']:.4f}",
                '召回率': f"{result['recall']:.4f}",
                'F1分数': f"{result['f1']:.4f}",
                '交叉验证': f"{result['cv_mean']:.4f}±{result['cv_std']:.4f}"
            })
    
    # 打印对比表
    if comparison_data:
        df_comparison = pd.DataFrame(comparison_data)
        print("\n模型性能对比表:")
        print(df_comparison.to_string(index=False))
        
        # 找出最佳模型
        best_model = max([r for r in results.values() if r is not None], 
                        key=lambda x: x['accuracy'])
        best_name = [name for name, result in results.items() 
                    if result is not None and result['accuracy'] == best_model['accuracy']][0]
        
        print(f"\n🏆 最佳模型: {best_name}")
        print(f"   准确率: {best_model['accuracy']:.4f}")
        print(f"   精确率: {best_model['precision']:.4f}")
        print(f"   召回率: {best_model['recall']:.4f}")
        print(f"   F1分数: {best_model['f1']:.4f}")
        
        # 打印最佳模型的详细报告
        print(f"\n{best_name} 详细分类报告:")
        print(best_model['classification_report'])
        
        # 打印混淆矩阵
        print(f"\n{best_name} 混淆矩阵:")
        cm = best_model['confusion_matrix']
        print("实际\\预测", end="")
        for i in range(cm.shape[1]):
            print(f"\t{i+1}", end="")
        print()
        for i in range(cm.shape[0]):
            print(f"   {i+1}   ", end="")
            for j in range(cm.shape[1]):
                print(f"\t{cm[i,j]}", end="")
            print()

def analyze_feature_importance(results, feature_names):
    """分析特征重要性（仅对随机森林）"""
    print("\n" + "="*80)
    print("特征重要性分析")
    print("="*80)
    
    if '随机森林' in results and results['随机森林'] is not None:
        rf_model = results['随机森林']['model']
        feature_importance = rf_model.feature_importances_
        
        # 创建特征重要性DataFrame
        importance_df = pd.DataFrame({
            '特征': feature_names,
            '重要性': feature_importance
        }).sort_values('重要性', ascending=False)
        
        print("\n随机森林特征重要性排序:")
        print(importance_df.to_string(index=False))
        
        # 可视化特征重要性（文本形式）
        print("\n特征重要性条形图:")
        max_importance = importance_df['重要性'].max()
        for _, row in importance_df.iterrows():
            bar_length = int(row['重要性'] / max_importance * 50)
            bar = '█' * bar_length + '░' * (50 - bar_length)
            print(f"{row['特征']:20} {bar} {row['重要性']:.4f}")
    else:
        print("随机森林模型不可用，无法分析特征重要性")

def main():
    """主函数"""
    print("=== 分类模型性能对比分析 ===")
    
    # 加载数据
    df = load_data()
    if df is None:
        print("无法加载数据，程序退出")
        return
    
    # 准备特征和目标变量
    X, y = prepare_features_and_target(df)
    if X is None or y is None:
        print("数据准备失败，程序退出")
        return
    
    # 训练和评估模型
    results, scaler, feature_names = train_and_evaluate_models(X, y)
    
    # 打印详细结果
    print_detailed_results(results)
    
    # 分析特征重要性
    analyze_feature_importance(results, feature_names)
    
    print("\n" + "="*80)
    print("分析完成！")
    print("="*80)

if __name__ == "__main__":
    main()
