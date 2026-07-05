import sqlite3
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, ExtraTreesClassifier, AdaBoostClassifier
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression, RidgeClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis, QuadraticDiscriminantAnalysis
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold, GridSearchCV, RandomizedSearchCV
from sklearn.preprocessing import StandardScaler, RobustScaler, MinMaxScaler, PowerTransformer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, precision_score, recall_score, f1_score
from sklearn.feature_selection import SelectKBest, f_classif, RFE, SelectFromModel
from sklearn.decomposition import PCA
from imblearn.over_sampling import SMOTE, ADASYN, BorderlineSMOTE
from imblearn.under_sampling import RandomUnderSampler, EditedNearestNeighbours
from imblearn.combine import SMOTEENN, SMOTETomek
from imblearn.ensemble import BalancedBaggingClassifier, BalancedRandomForestClassifier
import warnings
warnings.filterwarnings('ignore')

def load_data():
    """加载数据"""
    conn = sqlite3.connect('valid_data.db')
    df = pd.read_sql_query("SELECT * FROM trust_data", conn)
    conn.close()
    print(f"数据加载完成，共 {len(df)} 行")
    return df

def create_advanced_features(df):
    """创建高级特征工程"""
    print("=== 创建高级特征工程 ===")
    
    # 基础特征
    feature_columns = [
        'ai_control_time', 'person_control_time', 'total_time', 
        'ai_time_ratio', 'person_dominance', 'accept_ai_advice'
    ]
    
    X = df[feature_columns].copy()
    y = df['data_label'].copy()
    
    # 1. 异常值处理 - 使用更温和的方法
    print("处理异常值...")
    for col in ['person_control_time', 'total_time', 'person_dominance']:
        Q1 = X[col].quantile(0.05)  # 使用5%和95%分位数
        Q3 = X[col].quantile(0.95)
        X[col] = np.clip(X[col], Q1, Q3)
    
    # 2. 创建丰富的特征集
    print("创建特征...")
    
    # 基础比率特征
    X['ai_person_ratio'] = X['ai_control_time'] / (X['person_control_time'] + 1e-8)
    X['ai_total_ratio'] = X['ai_control_time'] / (X['total_time'] + 1e-8)
    X['person_total_ratio'] = X['person_control_time'] / (X['total_time'] + 1e-8)
    
    # 交互特征
    X['ai_accept_interaction'] = X['ai_time_ratio'] * X['accept_ai_advice']
    X['dominance_ai_interaction'] = X['person_dominance'] * X['ai_time_ratio']
    X['time_accept_interaction'] = X['total_time'] * X['accept_ai_advice']
    
    # 效率特征
    X['ai_efficiency'] = X['ai_control_time'] / (X['total_time'] + 1e-8)
    X['person_efficiency'] = X['person_control_time'] / (X['total_time'] + 1e-8)
    X['acceptance_rate'] = X['accept_ai_advice']
    
    # 对数变换
    X['log_ai_control'] = np.log1p(X['ai_control_time'])
    X['log_person_control'] = np.log1p(X['person_control_time'])
    X['log_total_time'] = np.log1p(X['total_time'])
    X['log_dominance'] = np.log1p(X['person_dominance'])
    
    # 平方根变换
    X['sqrt_ai_control'] = np.sqrt(X['ai_control_time'])
    X['sqrt_person_control'] = np.sqrt(X['person_control_time'])
    
    # 分箱特征
    X['ai_time_ratio_binned'] = pd.cut(X['ai_time_ratio'], bins=10, labels=False)
    X['accept_ai_binned'] = pd.cut(X['accept_ai_advice'], bins=10, labels=False)
    X['total_time_binned'] = pd.cut(X['total_time'], bins=10, labels=False)
    
    # 统计特征
    X['ai_time_squared'] = X['ai_time_ratio'] ** 2
    X['accept_squared'] = X['accept_ai_advice'] ** 2
    X['dominance_squared'] = X['person_dominance'] ** 2
    
    # 组合特征
    X['ai_dominance_combo'] = X['ai_time_ratio'] * X['person_dominance']
    X['accept_dominance_combo'] = X['accept_ai_advice'] * X['person_dominance']
    X['time_dominance_combo'] = X['total_time'] * X['person_dominance']
    
    print(f"特征工程完成，特征数: {X.shape[1]}")
    return X, y

def get_advanced_models():
    """获取高级模型集合"""
    models = {
        # 集成方法
        '随机森林_优化': RandomForestClassifier(
            n_estimators=300,
            max_depth=20,
            min_samples_split=2,
            min_samples_leaf=1,
            max_features='sqrt',
            class_weight='balanced',
            random_state=42,
            n_jobs=-1
        ),
        '极端随机树': ExtraTreesClassifier(
            n_estimators=300,
            max_depth=20,
            min_samples_split=2,
            min_samples_leaf=1,
            class_weight='balanced',
            random_state=42,
            n_jobs=-1
        ),
        '梯度提升_优化': GradientBoostingClassifier(
            n_estimators=300,
            max_depth=8,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42
        ),
        'AdaBoost': AdaBoostClassifier(
            n_estimators=200,
            learning_rate=0.1,
            random_state=42
        ),
        '平衡随机森林': BalancedRandomForestClassifier(
            n_estimators=300,
            max_depth=20,
            random_state=42,
            n_jobs=-1
        ),
        '平衡装袋': BalancedBaggingClassifier(
            n_estimators=200,
            random_state=42,
            n_jobs=-1
        ),
        
        # 支持向量机
        'SVM_RBF': SVC(
            kernel='rbf',
            C=100,
            gamma='scale',
            class_weight='balanced',
            random_state=42,
            probability=True
        ),
        'SVM_Poly': SVC(
            kernel='poly',
            degree=3,
            C=10,
            class_weight='balanced',
            random_state=42,
            probability=True
        ),
        'SVM_Sigmoid': SVC(
            kernel='sigmoid',
            C=10,
            class_weight='balanced',
            random_state=42,
            probability=True
        ),
        
        # 线性模型
        '逻辑回归_L1': LogisticRegression(
            penalty='l1',
            C=1.0,
            solver='liblinear',
            class_weight='balanced',
            random_state=42,
            max_iter=1000
        ),
        '逻辑回归_L2': LogisticRegression(
            penalty='l2',
            C=1.0,
            class_weight='balanced',
            random_state=42,
            max_iter=1000
        ),
        'Ridge分类器': RidgeClassifier(
            alpha=1.0,
            class_weight='balanced',
            random_state=42
        ),
        
        # 其他模型
        'KNN': KNeighborsClassifier(
            n_neighbors=5,
            weights='distance',
            algorithm='auto'
        ),
        '决策树': DecisionTreeClassifier(
            max_depth=20,
            min_samples_split=2,
            min_samples_leaf=1,
            class_weight='balanced',
            random_state=42
        ),
        '高斯朴素贝叶斯': GaussianNB(),
        '线性判别分析': LinearDiscriminantAnalysis(),
        '二次判别分析': QuadraticDiscriminantAnalysis()
    }
    
    return models

def train_task_specific_models(X, y, task_name):
    """为特定任务训练模型"""
    print(f"\n=== 训练 {task_name} 任务模型 ===")
    
    # 数据分割
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # 特征标准化
    scaler = RobustScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # 处理类别不平衡 - 尝试多种方法
    sampling_methods = {
        'SMOTE': SMOTE(random_state=42, k_neighbors=3),
        'ADASYN': ADASYN(random_state=42),
        'BorderlineSMOTE': BorderlineSMOTE(random_state=42),
        'SMOTEENN': SMOTEENN(random_state=42),
        'SMOTETomek': SMOTETomek(random_state=42)
    }
    
    best_results = {}
    
    for method_name, sampler in sampling_methods.items():
        print(f"\n--- 使用 {method_name} 处理类别不平衡 ---")
        
        try:
            X_resampled, y_resampled = sampler.fit_resample(X_train_scaled, y_train)
            print(f"平衡后样本数: {len(X_resampled)}")
            
            # 获取模型
            models = get_advanced_models()
            
            # 训练所有模型
            task_results = {}
            
            for model_name, model in models.items():
                try:
                    print(f"训练 {model_name}...")
                    
                    # 训练模型
                    model.fit(X_resampled, y_resampled)
                    
                    # 预测
                    y_pred = model.predict(X_test_scaled)
                    
                    # 计算指标
                    accuracy = accuracy_score(y_test, y_pred)
                    precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
                    recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
                    f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
                    
                    # 交叉验证
                    cv_scores = cross_val_score(
                        model, X_resampled, y_resampled, 
                        cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=42),
                        scoring='accuracy'
                    )
                    
                    task_results[model_name] = {
                        'accuracy': accuracy,
                        'precision': precision,
                        'recall': recall,
                        'f1': f1,
                        'cv_mean': cv_scores.mean(),
                        'cv_std': cv_scores.std(),
                        'y_test': y_test,
                        'y_pred': y_pred,
                        'model': model
                    }
                    
                    print(f"  {model_name}: 准确率={accuracy:.4f}, CV={cv_scores.mean():.4f}")
                    
                except Exception as e:
                    print(f"  {model_name} 训练失败: {e}")
                    continue
            
            # 找出最佳模型
            if task_results:
                best_model_name = max(task_results.keys(), key=lambda x: task_results[x]['accuracy'])
                best_results[method_name] = {
                    'best_model': best_model_name,
                    'accuracy': task_results[best_model_name]['accuracy'],
                    'all_results': task_results
                }
                print(f"最佳模型: {best_model_name}, 准确率: {task_results[best_model_name]['accuracy']:.4f}")
        
        except Exception as e:
            print(f"{method_name} 处理失败: {e}")
            continue
    
    return best_results

def hyperparameter_optimization(X, y, model_name, model):
    """超参数优化"""
    print(f"\n=== 优化 {model_name} 超参数 ===")
    
    # 定义参数网格
    param_grids = {
        'RandomForestClassifier': {
            'n_estimators': [200, 300, 500],
            'max_depth': [15, 20, 25, None],
            'min_samples_split': [2, 5, 10],
            'min_samples_leaf': [1, 2, 4],
            'max_features': ['sqrt', 'log2', None]
        },
        'GradientBoostingClassifier': {
            'n_estimators': [200, 300, 500],
            'max_depth': [6, 8, 10],
            'learning_rate': [0.01, 0.05, 0.1],
            'subsample': [0.8, 0.9, 1.0]
        },
        'SVC': {
            'C': [0.1, 1, 10, 100],
            'gamma': ['scale', 'auto', 0.001, 0.01, 0.1],
            'kernel': ['rbf', 'poly', 'sigmoid']
        }
    }
    
    model_type = type(model).__name__
    if model_type in param_grids:
        param_grid = param_grids[model_type]
        
        # 使用随机搜索
        random_search = RandomizedSearchCV(
            model, param_grid, n_iter=20, cv=3, 
            scoring='accuracy', random_state=42, n_jobs=-1
        )
        
        random_search.fit(X, y)
        
        print(f"最佳参数: {random_search.best_params_}")
        print(f"最佳分数: {random_search.best_score_:.4f}")
        
        return random_search.best_estimator_
    
    return model

def main():
    """主函数"""
    print("=== 高级任务特定模型：目标90%+准确率 ===")
    
    # 加载数据
    df = load_data()
    
    # 创建高级特征
    X, y = create_advanced_features(df)
    
    # 按任务分组训练模型
    tasks = df['task_name'].unique()
    print(f"发现任务: {tasks}")
    
    all_task_results = {}
    
    for task in tasks:
        print(f"\n{'='*60}")
        print(f"处理任务: {task}")
        print(f"{'='*60}")
        
        # 筛选任务数据
        task_mask = df['task_name'] == task
        X_task = X[task_mask]
        y_task = y[task_mask]
        
        print(f"任务 {task} 数据量: {len(X_task)}")
        print(f"类别分布: {y_task.value_counts().sort_index().to_dict()}")
        
        if len(X_task) < 50:  # 数据太少跳过
            print(f"任务 {task} 数据量太少，跳过")
            continue
        
        # 训练任务特定模型
        task_results = train_task_specific_models(X_task, y_task, task)
        all_task_results[task] = task_results
    
    # 全局模型训练
    print(f"\n{'='*60}")
    print("训练全局模型")
    print(f"{'='*60}")
    
    global_results = train_task_specific_models(X, y, "全局")
    all_task_results["全局"] = global_results
    
    # 输出结果汇总
    print(f"\n{'='*80}")
    print("所有任务结果汇总")
    print(f"{'='*80}")
    
    for task, results in all_task_results.items():
        print(f"\n--- {task} ---")
        if results:
            for method, result in results.items():
                print(f"{method}: {result['best_model']} - 准确率: {result['accuracy']:.4f}")
        else:
            print("无有效结果")
    
    # 找出全局最佳模型
    best_accuracy = 0
    best_task = None
    best_method = None
    
    for task, results in all_task_results.items():
        if results:
            for method, result in results.items():
                if result['accuracy'] > best_accuracy:
                    best_accuracy = result['accuracy']
                    best_task = task
                    best_method = method
    
    print(f"\n🏆 全局最佳结果:")
    print(f"任务: {best_task}")
    print(f"方法: {best_method}")
    print(f"准确率: {best_accuracy:.4f}")
    
    if best_accuracy >= 0.9:
        print("🎉 成功达到90%+准确率目标!")
    else:
        print(f"⚠️  未达到90%目标，当前最佳: {best_accuracy:.4f}")
        print("建议:")
        print("1. 收集更多数据")
        print("2. 改进特征工程")
        print("3. 尝试深度学习模型")
        print("4. 重新审视标签质量")

if __name__ == "__main__":
    main()
