"""
SVM模型性能指标计算和分析工具

功能特性:
1. 基础性能指标：RMSE、准确率、精确率、召回率、F1分数
2. 混淆矩阵分析：原始和标准化混淆矩阵
3. 分类报告：详细的每类别性能指标
4. 多分类指标：宏平均、加权平均、Cohen's Kappa、Matthews相关系数
5. 类别分布分析：真实标签vs预测标签分布，类别平衡度
6. 每折性能分析：交叉验证中每折的详细性能
7. 错误分析：错误类型统计和最常见错误模式
8. 类别性能分析：每个类别的精确率、召回率、F1分数
9. 可视化图表：混淆矩阵热力图、性能趋势图、类别分布图、雷达图

使用方法:
python step4_calculate_metrics_from_results.py [选项]

选项:
--file1 FILE1        第一个fold_results文件路径 (默认: fold_results_20250908_191520.json)
--file2 FILE2        第二个fold_results文件路径 (默认: fold_results_20250909_110628.json)
--visualize          生成可视化图表
--output-dir DIR     可视化图表输出目录 (默认: svm_analysis_plots)

示例:
python step4_calculate_metrics_from_results.py --visualize
python step4_calculate_metrics_from_results.py --file1 my_results.json --visualize --output-dir my_plots
"""

import json
import numpy as np
import pandas as pd
import glob
import os
from datetime import datetime
from pathlib import Path
import argparse
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (
    confusion_matrix, classification_report, roc_curve, auc, 
    precision_recall_curve, average_precision_score,
    cohen_kappa_score, matthews_corrcoef
)
from sklearn.preprocessing import label_binarize
from collections import Counter

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"


def latest_output_file(pattern):
    matches = sorted(OUTPUT_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(matches[0]) if matches else None

def calculate_model_metrics_from_file(fold_results_file):
    """
    从fold_results文件计算模型性能指标
    
    参数:
    - fold_results_file: fold_results JSON文件路径
    
    返回:
    - metrics: 包含所有指标的字典
    """
    try:
        print(f"正在读取文件: {fold_results_file}")
        
        # 读取fold_results文件
        with open(fold_results_file, 'r', encoding='utf-8') as f:
            fold_results = json.load(f)
        
        print(f"文件读取成功，包含 {len(fold_results['fold_details'])} 折数据")
        
        # 从折结果中提取数据
        all_predictions = np.array(fold_results['all_predictions'])
        all_true_labels = np.array(fold_results['all_true_labels'])
        fold_accuracies = fold_results['fold_accuracies']
        
        # 1. 模型跟踪性能：计算RMSE
        rmse = np.sqrt(np.mean((all_predictions - all_true_labels)/5 ** 2)) # 1-5归到0-1
        
        # 2. 模型分辨率：计算最高和最低准确率的差
        max_accuracy = max(fold_accuracies)
        min_accuracy = min(fold_accuracies)
        resolution = max_accuracy - min_accuracy
        
        # 3. 模型泛化性：计算平均准确率和精确率
        generalization_accuracy = np.mean(fold_accuracies)
        generalization_accuracy_std = np.std(fold_accuracies)
        
        # 计算精确率（宏平均）
        from sklearn.metrics import precision_score
        precision_scores = []
        for fold_detail in fold_results['fold_details']:
            y_true = np.array(fold_detail['true_labels'])
            y_pred = np.array(fold_detail['predictions'])
            precision = precision_score(y_true, y_pred, average='macro', zero_division=0)
            precision_scores.append(precision)
        
        generalization_precision = np.mean(precision_scores)
        generalization_precision_std = np.std(precision_scores)
        
        # 计算额外的SVM通用分析指标
        svm_analysis = calculate_svm_analysis_metrics(all_predictions, all_true_labels, fold_results)
        
        # 整理结果
        metrics = {
            'tracking_performance': {
                'rmse': float(rmse),
                'description': '模型跟踪性能：RMSE'
            },
            'resolution': {
                'max_accuracy': float(max_accuracy),
                'min_accuracy': float(min_accuracy),
                'difference': float(resolution),
                'description': '模型分辨率：最高与最低准确率差'
            },
            'generalization': {
                'mean_accuracy': float(generalization_accuracy),
                'std_accuracy': float(generalization_accuracy_std),
                'mean_precision': float(generalization_precision),
                'std_precision': float(generalization_precision_std),
                'description': '模型泛化性：平均准确率和精确率'
            },
            'svm_analysis': svm_analysis,
            'detailed_results': {
                'fold_accuracies': [float(acc) for acc in fold_accuracies],
                'predictions': all_predictions.tolist(),
                'true_labels': all_true_labels.tolist()
            },
            'file_info': {
                'source_file': fold_results_file,
                'calculation_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'n_folds': len(fold_results['fold_details']),
                'n_samples': len(all_predictions)
            }
        }
        
        return metrics
        
    except Exception as e:
        print(f"计算模型指标错误: {e}")
        import traceback
        traceback.print_exc()
        return None

def calculate_svm_analysis_metrics(predictions, true_labels, fold_results):
    """
    计算SVM模型的通用分析指标
    
    参数:
    - predictions: 预测结果数组
    - true_labels: 真实标签数组
    - fold_results: 折结果字典
    
    返回:
    - svm_analysis: SVM分析指标字典
    """
    try:
        # 确保标签是整数类型
        predictions = np.array(predictions, dtype=int)
        true_labels = np.array(true_labels, dtype=int)
        
        # 获取类别信息
        unique_labels = np.unique(np.concatenate([predictions, true_labels]))
        n_classes = len(unique_labels)
        
        # 1. 混淆矩阵分析
        cm = confusion_matrix(true_labels, predictions)
        cm_normalized = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
        
        # 2. 分类报告
        class_report = classification_report(true_labels, predictions, 
                                           target_names=[f'类别{i}' for i in unique_labels],
                                           output_dict=True, zero_division=0)
        
        # 3. 多分类指标
        from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
        
        accuracy = accuracy_score(true_labels, predictions)
        precision_macro = precision_score(true_labels, predictions, average='macro', zero_division=0)
        recall_macro = recall_score(true_labels, predictions, average='macro', zero_division=0)
        f1_macro = f1_score(true_labels, predictions, average='macro', zero_division=0)
        
        precision_weighted = precision_score(true_labels, predictions, average='weighted', zero_division=0)
        recall_weighted = recall_score(true_labels, predictions, average='weighted', zero_division=0)
        f1_weighted = f1_score(true_labels, predictions, average='weighted', zero_division=0)
        
        # 4. Cohen's Kappa 和 Matthews相关系数
        kappa = cohen_kappa_score(true_labels, predictions)
        mcc = matthews_corrcoef(true_labels, predictions)
        
        # 5. 类别分布分析
        true_distribution = Counter(true_labels)
        pred_distribution = Counter(predictions)
        
        # 6. 每折的详细分析
        fold_analysis = []
        for i, fold_detail in enumerate(fold_results['fold_details']):
            fold_true = np.array(fold_detail['true_labels'], dtype=int)
            fold_pred = np.array(fold_detail['predictions'], dtype=int)
            
            fold_accuracy = accuracy_score(fold_true, fold_pred)
            fold_precision = precision_score(fold_true, fold_pred, average='macro', zero_division=0)
            fold_recall = recall_score(fold_true, fold_pred, average='macro', zero_division=0)
            fold_f1 = f1_score(fold_true, fold_pred, average='macro', zero_division=0)
            
            fold_analysis.append({
                'fold': i + 1,
                'accuracy': float(fold_accuracy),
                'precision': float(fold_precision),
                'recall': float(fold_recall),
                'f1': float(fold_f1),
                'n_samples': len(fold_true)
            })
        
        # 7. 错误分析
        error_analysis = analyze_prediction_errors(true_labels, predictions, unique_labels)
        
        # 8. 类别性能分析
        class_performance = analyze_class_performance(true_labels, predictions, unique_labels)
        
        svm_analysis = {
            'confusion_matrix': {
                'matrix': cm.tolist(),
                'normalized_matrix': cm_normalized.tolist(),
                'description': '混淆矩阵（原始和标准化）'
            },
            'classification_report': class_report,
            'overall_metrics': {
                'accuracy': float(accuracy),
                'precision_macro': float(precision_macro),
                'recall_macro': float(recall_macro),
                'f1_macro': float(f1_macro),
                'precision_weighted': float(precision_weighted),
                'recall_weighted': float(recall_weighted),
                'f1_weighted': float(f1_weighted),
                'kappa': float(kappa),
                'mcc': float(mcc),
                'description': '整体性能指标'
            },
            'class_distribution': {
                'true_labels': dict(true_distribution),
                'predictions': dict(pred_distribution),
                'n_classes': int(n_classes),
                'class_balance': calculate_class_balance(true_distribution),
                'description': '类别分布分析'
            },
            'fold_analysis': fold_analysis,
            'error_analysis': error_analysis,
            'class_performance': class_performance,
            'n_samples': len(predictions),
            'n_classes': int(n_classes)
        }
        
        return svm_analysis
        
    except Exception as e:
        print(f"计算SVM分析指标时出错: {e}")
        import traceback
        traceback.print_exc()
        return {}

def analyze_prediction_errors(true_labels, predictions, unique_labels):
    """
    分析预测错误
    
    参数:
    - true_labels: 真实标签
    - predictions: 预测标签
    - unique_labels: 唯一标签列表
    
    返回:
    - error_analysis: 错误分析字典
    """
    try:
        # 找出错误预测的样本
        error_mask = true_labels != predictions
        error_indices = np.where(error_mask)[0]
        
        # 错误类型分析
        error_types = {}
        for true_label in unique_labels:
            for pred_label in unique_labels:
                if true_label != pred_label:
                    mask = (true_labels == true_label) & (predictions == pred_label)
                    count = np.sum(mask)
                    if count > 0:
                        error_types[f'{true_label}->{pred_label}'] = int(count)
        
        # 最常见的错误类型
        most_common_errors = sorted(error_types.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'total_errors': int(np.sum(error_mask)),
            'error_rate': float(np.mean(error_mask)),
            'error_types': error_types,
            'most_common_errors': most_common_errors,
            'error_indices': error_indices.tolist()[:100]  # 只保存前100个错误索引
        }
        
    except Exception as e:
        print(f"分析预测错误时出错: {e}")
        return {}

def analyze_class_performance(true_labels, predictions, unique_labels):
    """
    分析每个类别的性能
    
    参数:
    - true_labels: 真实标签
    - predictions: 预测标签
    - unique_labels: 唯一标签列表
    
    返回:
    - class_performance: 类别性能字典
    """
    try:
        class_performance = {}
        
        for label in unique_labels:
            # 该类别的真实样本
            true_mask = true_labels == label
            true_count = np.sum(true_mask)
            
            # 该类别的预测样本
            pred_mask = predictions == label
            pred_count = np.sum(pred_mask)
            
            # 正确预测的样本
            correct_mask = (true_labels == label) & (predictions == label)
            correct_count = np.sum(correct_mask)
            
            # 计算指标
            precision = correct_count / pred_count if pred_count > 0 else 0
            recall = correct_count / true_count if true_count > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            
            class_performance[f'class_{label}'] = {
                'true_count': int(true_count),
                'pred_count': int(pred_count),
                'correct_count': int(correct_count),
                'precision': float(precision),
                'recall': float(recall),
                'f1': float(f1)
            }
        
        return class_performance
        
    except Exception as e:
        print(f"分析类别性能时出错: {e}")
        return {}

def calculate_class_balance(distribution):
    """
    计算类别平衡度
    
    参数:
    - distribution: 类别分布字典
    
    返回:
    - balance_metrics: 平衡度指标
    """
    try:
        counts = list(distribution.values())
        if len(counts) == 0:
            return {}
        
        counts = np.array(counts)
        mean_count = np.mean(counts)
        std_count = np.std(counts)
        cv = std_count / mean_count if mean_count > 0 else 0
        
        return {
            'mean_count': float(mean_count),
            'std_count': float(std_count),
            'coefficient_of_variation': float(cv),
            'is_balanced': cv < 0.3  # 变异系数小于0.3认为相对平衡
        }
        
    except Exception as e:
        print(f"计算类别平衡度时出错: {e}")
        return {}

def save_metrics_to_file(metrics, output_file=None):
    """
    保存指标到JSON文件
    
    参数:
    - metrics: 指标字典
    - output_file: 输出文件名，如果为None则自动生成
    """
    try:
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"calculated_metrics_{timestamp}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
        print(f"\n指标已保存到: {output_file}")
        
    except Exception as e:
        print(f"保存指标文件时出错: {e}")

def main():
    """主函数"""
    print("脚本开始运行...")
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='SVM模型性能指标计算和分析工具')
    parser.add_argument('--file1', default=None, 
                       help='第一个fold_results文件路径')
    parser.add_argument('--file2', default=None, 
                       help='第二个fold_results文件路径')
    parser.add_argument('--visualize', action='store_true', 
                       help='是否生成可视化图表')
    parser.add_argument('--output-dir', default=str(OUTPUT_DIR / "svm_analysis_plots"), 
                       help='可视化图表输出目录')
    
    args = parser.parse_args()
    
    # 指定要处理的两个文件
    fold_results_file1 = args.file1 or latest_output_file("fold_results_*.json")
    fold_results_file2 = args.file2 or fold_results_file1
    
    print("=== 模型性能指标计算工具 ===")
    print(f"处理文件1: {fold_results_file1}")
    print(f"处理文件2: {fold_results_file2}")
    
    # 检查文件是否存在
    if not fold_results_file1 or not os.path.exists(fold_results_file1):
        print(f"文件不存在: {fold_results_file1}")
        return
    
    if not fold_results_file2 or not os.path.exists(fold_results_file2):
        print(f"文件不存在: {fold_results_file2}")
        return
    
    # 计算第一个文件的指标
    print(f"\n=== 处理第一个文件 ===")
    metrics1 = calculate_model_metrics_from_file(fold_results_file1)
    
    # 计算第二个文件的指标
    print(f"\n=== 处理第二个文件 ===")
    metrics2 = calculate_model_metrics_from_file(fold_results_file2)
    
    if metrics1 is not None and metrics2 is not None:
        # 计算模型一致性
        print(f"\n=== 计算模型一致性 ===")
        accuracy1 = metrics1['generalization']['mean_accuracy']
        accuracy2 = metrics2['generalization']['mean_accuracy']
        precision1 = metrics1['generalization']['mean_precision']
        precision2 = metrics2['generalization']['mean_precision']
        
        # 计算准确率一致性
        accuracy_consistency = abs(accuracy1 - accuracy2)
        # 计算精确率一致性
        precision_consistency = abs(precision1 - precision2)
        
        # 打印最终性能结果
        print(f"\n=== 最终性能结果 ===")
        print(f"1. 模型跟踪性能 (RMSE):")
        print(f"   文件1: {metrics1['tracking_performance']['rmse']*100:.2f}%")
        # print(f"   文件2: {metrics2['tracking_performance']['rmse']*100:.2f}%")
        
        print(f"\n2. 模型分辨率:")
        print(f"   文件1: {metrics1['resolution']['difference']*100:.2f}% (最高: {metrics1['resolution']['max_accuracy']*100:.2f}%, 最低: {metrics1['resolution']['min_accuracy']*100:.2f}%)")
        # print(f"   文件2: {metrics2['resolution']['difference']*100:.2f}% (最高: {metrics2['resolution']['max_accuracy']*100:.2f}%, 最低: {metrics2['resolution']['min_accuracy']*100:.2f}%)")
        
        print(f"\n3. 模型泛化性:")
        print(f"   文件1 - 准确率: {metrics1['generalization']['mean_accuracy']*100:.2f}% ± {metrics1['generalization']['std_accuracy']*100:.2f}%, 精确率: {metrics1['generalization']['mean_precision']*100:.2f}% ± {metrics1['generalization']['std_precision']*100:.2f}%")
        # print(f"   文件2 - 准确率: {metrics2['generalization']['mean_accuracy']*100:.2f}% ± {metrics2['generalization']['std_accuracy']*100:.2f}%, 精确率: {metrics2['generalization']['mean_precision']*100:.2f}% ± {metrics2['generalization']['std_precision']*100:.2f}%")
        
        print(f"\n4. 模型一致性:")
        print(f"   准确率一致性: {accuracy_consistency*100:.2f}%")
        print(f"   精确率一致性: {precision_consistency*100:.2f}%")
        
        # 生成并保存可视化图表
        print(f"\n=== 生成并保存可视化图表 ===")
        generate_svm_visualizations(metrics1, args.output_dir)
        
        # 生成超参数热力图
        print(f"\n=== 生成超参数热力图 ===")
        hyperparameter_file = latest_output_file("hyperparameter_search_results_*.csv")
        if hyperparameter_file and os.path.exists(hyperparameter_file):
            plot_hyperparameter_heatmap(hyperparameter_file, args.output_dir)
        else:
            print(f"超参数搜索结果文件不存在: {hyperparameter_file}")
        
        # 直接显示SVM分析图片
        print(f"\n=== 显示SVM分析图片 ===")
        try:
            display_svm_analysis_plots(metrics1)
        except Exception as e:
            print(f"显示图片时出错: {e}")
            print("可能是matplotlib显示环境问题，尝试使用非交互式后端...")
            import matplotlib
            matplotlib.use('Agg')  # 使用非交互式后端
            display_svm_analysis_plots(metrics1)
        
    else:
        print("计算指标失败")

def display_svm_analysis_plots(metrics):
    """
    直接显示SVM分析图片（不保存到文件）
    
    参数:
    - metrics: 包含SVM分析的指标字典
    """
    try:
        if 'svm_analysis' not in metrics:
            print("未找到SVM分析数据，无法显示图片")
            return
        
        svm_analysis = metrics['svm_analysis']
        
        # 设置中文字体和字体大小
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['font.size'] = 12
        plt.rcParams['axes.titlesize'] = 16
        plt.rcParams['axes.labelsize'] = 14
        plt.rcParams['xtick.labelsize'] = 12
        plt.rcParams['ytick.labelsize'] = 12
        plt.rcParams['legend.fontsize'] = 12
        
        # 1. 混淆矩阵热力图
        cm_info = svm_analysis.get('confusion_matrix', {})
        if cm_info and 'matrix' in cm_info:
            matrix = np.array(cm_info['matrix'])
            normalized_matrix = np.array(cm_info.get('normalized_matrix', matrix))
            
            # 获取类别标签（应该是1-5）
            unique_labels = sorted(svm_analysis.get('class_distribution', {}).get('true_labels', {}).keys())
            if not unique_labels:
                # 如果没有类别分布信息，从混淆矩阵大小推断
                unique_labels = list(range(1, matrix.shape[0] + 1))
            
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
            
            # 原始混淆矩阵
            sns.heatmap(matrix, annot=True, fmt='d', cmap='Blues', ax=ax1,
                       xticklabels=unique_labels, yticklabels=unique_labels,
                       annot_kws={'size': 14})
            ax1.set_title('混淆矩阵 (原始)', fontsize=18)
            ax1.set_xlabel('预测标签', fontsize=16)
            ax1.set_ylabel('真实标签', fontsize=16)
            
            # 标准化混淆矩阵
            sns.heatmap(normalized_matrix, annot=True, fmt='.3f', cmap='Blues', ax=ax2,
                       xticklabels=unique_labels, yticklabels=unique_labels,
                       annot_kws={'size': 14})
            ax2.set_title('混淆矩阵 (标准化)', fontsize=18)
            ax2.set_xlabel('预测标签', fontsize=16)
            ax2.set_ylabel('真实标签', fontsize=16)
            
            plt.tight_layout()
            plt.show()
        
        # 2. 每折性能对比图
        fold_analysis = svm_analysis.get('fold_analysis', [])
        if fold_analysis:
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
            
            folds = [fold['fold'] for fold in fold_analysis]
            accuracies = [fold['accuracy'] for fold in fold_analysis]
            precisions = [fold['precision'] for fold in fold_analysis]
            recalls = [fold['recall'] for fold in fold_analysis]
            f1s = [fold['f1'] for fold in fold_analysis]
            
            # 计算所有指标的范围，用于设置合适的y轴范围
            all_values = accuracies + precisions + recalls + f1s
            min_val = min(all_values)
            max_val = max(all_values)
            # 添加一些边距，让图表更美观
            margin = (max_val - min_val) * 0.1
            y_min = max(0, min_val - margin)
            y_max = min(1, max_val + margin)
            
            # 准确率
            ax1.plot(folds, accuracies, 'o-', linewidth=2, markersize=8)
            ax1.set_title('每折准确率', fontsize=18)
            ax1.set_xlabel('折数', fontsize=16)
            ax1.set_ylabel('准确率', fontsize=16)
            ax1.grid(True, alpha=0.3)
            ax1.set_ylim(y_min, y_max)
            
            # 精确率
            ax2.plot(folds, precisions, 'o-', linewidth=2, markersize=8, color='orange')
            ax2.set_title('每折精确率', fontsize=18)
            ax2.set_xlabel('折数', fontsize=16)
            ax2.set_ylabel('精确率', fontsize=16)
            ax2.grid(True, alpha=0.3)
            ax2.set_ylim(y_min, y_max)
            
            # 召回率
            ax3.plot(folds, recalls, 'o-', linewidth=2, markersize=8, color='green')
            ax3.set_title('每折召回率', fontsize=18)
            ax3.set_xlabel('折数', fontsize=16)
            ax3.set_ylabel('召回率', fontsize=16)
            ax3.grid(True, alpha=0.3)
            ax3.set_ylim(y_min, y_max)
            
            # F1分数
            ax4.plot(folds, f1s, 'o-', linewidth=2, markersize=8, color='red')
            ax4.set_title('每折F1分数', fontsize=18)
            ax4.set_xlabel('折数', fontsize=16)
            ax4.set_ylabel('F1分数', fontsize=16)
            ax4.grid(True, alpha=0.3)
            ax4.set_ylim(y_min, y_max)
            
            plt.tight_layout()
            plt.show()
        
        # 打印混淆矩阵详细信息
        print_confusion_matrix_details(svm_analysis)
        
        # 打印每折性能详细信息
        print_fold_performance_details(svm_analysis)
        
        print("所有SVM分析图片已显示完成！")
        
    except Exception as e:
        print(f"显示SVM分析图片时出错: {e}")
        import traceback
        traceback.print_exc()

def print_confusion_matrix_details(svm_analysis):
    """
    打印混淆矩阵详细信息
    
    参数:
    - svm_analysis: SVM分析结果字典
    """
    try:
        cm_info = svm_analysis.get('confusion_matrix', {})
        if not cm_info or 'matrix' not in cm_info:
            return
        
        matrix = np.array(cm_info['matrix'])
        normalized_matrix = np.array(cm_info.get('normalized_matrix', matrix))
        
        # 获取类别标签
        class_labels = sorted(svm_analysis.get('class_distribution', {}).get('true_labels', {}).keys())
        if not class_labels:
            class_labels = list(range(1, matrix.shape[0] + 1))
        
        print(f"\n=== 混淆矩阵详细信息 ===")
        print(f"类别标签: {class_labels}")
        print(f"\n原始混淆矩阵:")
        print("     ", end="")
        for label in class_labels:
            print(f"{label:>8}", end="")
        print("  (预测)")
        
        for i, true_label in enumerate(class_labels):
            print(f"{true_label:>3} |", end="")
            for j in range(len(class_labels)):
                print(f"{matrix[i, j]:>8}", end="")
            print()
        
        print("\n标准化混淆矩阵 (每行和为1):")
        print("     ", end="")
        for label in class_labels:
            print(f"{label:>8}", end="")
        print("  (预测)")
        
        for i, true_label in enumerate(class_labels):
            print(f"{true_label:>3} |", end="")
            for j in range(len(class_labels)):
                print(f"{normalized_matrix[i, j]:>8.3f}", end="")
            print()
        
        # 计算并显示每类别的准确率
        print(f"\n各类别分类准确率:")
        diagonal = np.diag(matrix)
        row_sums = np.sum(matrix, axis=1)
        for i, label in enumerate(class_labels):
            if row_sums[i] > 0:
                accuracy = diagonal[i] / row_sums[i]
                print(f"  类别{label}: {accuracy*100:.2f}% ({diagonal[i]}/{row_sums[i]})")
        
    except Exception as e:
        print(f"打印混淆矩阵详细信息时出错: {e}")

def print_fold_performance_details(svm_analysis):
    """
    打印每折性能详细信息
    
    参数:
    - svm_analysis: SVM分析结果字典
    """
    try:
        fold_analysis = svm_analysis.get('fold_analysis', [])
        if not fold_analysis:
            return
        
        print(f"\n=== 每折性能详细信息 ===")
        print(f"{'折数':<4} {'准确率':<8} {'精确率':<8} {'召回率':<8} {'F1分数':<8} {'样本数':<6}")
        print("-" * 50)
        
        for fold in fold_analysis:
            print(f"{fold['fold']:<4} "
                  f"{fold['accuracy']*100:<8.2f} "
                  f"{fold['precision']*100:<8.2f} "
                  f"{fold['recall']*100:<8.2f} "
                  f"{fold['f1']*100:<8.2f} "
                  f"{fold['n_samples']:<6}")
        
        # 计算统计信息
        accuracies = [fold['accuracy'] for fold in fold_analysis]
        precisions = [fold['precision'] for fold in fold_analysis]
        recalls = [fold['recall'] for fold in fold_analysis]
        f1s = [fold['f1'] for fold in fold_analysis]
        
        print("-" * 50)
        print(f"{'平均':<4} "
              f"{np.mean(accuracies)*100:<8.2f} "
              f"{np.mean(precisions)*100:<8.2f} "
              f"{np.mean(recalls)*100:<8.2f} "
              f"{np.mean(f1s)*100:<8.2f}")
        
        print(f"{'标准差':<4} "
              f"{np.std(accuracies)*100:<8.2f} "
              f"{np.std(precisions)*100:<8.2f} "
              f"{np.std(recalls)*100:<8.2f} "
              f"{np.std(f1s)*100:<8.2f}")
        
        # 找出最佳和最差折
        best_fold_idx = np.argmax(accuracies)
        worst_fold_idx = np.argmin(accuracies)
        
        print(f"\n最佳折: 第{best_fold_idx+1}折 (准确率: {accuracies[best_fold_idx]*100:.2f}%)")
        print(f"最差折: 第{worst_fold_idx+1}折 (准确率: {accuracies[worst_fold_idx]*100:.2f}%)")
        print(f"性能差异: {(accuracies[best_fold_idx]-accuracies[worst_fold_idx])*100:.2f}个百分点")
        
    except Exception as e:
        print(f"打印每折性能详细信息时出错: {e}")

def plot_hyperparameter_heatmap(csv_file, output_dir="svm_analysis_plots"):
    """
    绘制SVM超参数配置下的10折平均准确率热力图
    
    参数:
    - csv_file: 超参数搜索结果CSV文件路径
    - output_dir: 输出目录
    """
    try:
        print(f"正在读取超参数搜索结果文件: {csv_file}")
        
        # 读取CSV文件
        df = pd.read_csv(csv_file)
        
        # 提取C和gamma参数以及平均测试分数
        c_values = df['param_C'].values
        gamma_values = df['param_gamma'].values
        mean_scores = df['mean_test_score'].values
        
        # 获取唯一的C和gamma值并排序
        unique_c = sorted(df['param_C'].unique())
        unique_gamma = sorted(df['param_gamma'].unique())
        
        print(f"找到 {len(unique_c)} 个不同的C值: {unique_c}")
        print(f"找到 {len(unique_gamma)} 个不同的gamma值: {unique_gamma}")
        
        # 创建热力图数据矩阵
        heatmap_data = np.zeros((len(unique_gamma), len(unique_c)))
        
        # 填充数据矩阵
        for i, row in df.iterrows():
            c_idx = unique_c.index(row['param_C'])
            gamma_idx = unique_gamma.index(row['param_gamma'])
            heatmap_data[gamma_idx, c_idx] = row['mean_test_score']
        
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['font.family'] = 'sans-serif'
        
        # 创建热力图
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # 使用seaborn绘制热力图
        sns.heatmap(heatmap_data, 
                   xticklabels=[f'{c:.3f}' if c < 1 else f'{c:.0f}' for c in unique_c],
                   yticklabels=[f'{g:.3f}' if g < 1 else f'{g:.0f}' for g in unique_gamma],
                   annot=True, 
                   fmt='.3f',
                   cmap='YlOrRd',
                   cbar_kws={'label': '10折平均准确率'},
                   ax=ax)
        
        ax.set_title('SVM超参数配置下的10折平均准确率热力图', fontsize=16, fontweight='bold')
        ax.set_xlabel('C参数 (正则化强度)', fontsize=14)
        ax.set_ylabel('Gamma参数 (RBF核函数参数)', fontsize=14)
        
        # 旋转x轴标签以避免重叠
        plt.xticks(rotation=45)
        plt.yticks(rotation=0)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图片
        os.makedirs(output_dir, exist_ok=True)
        output_path = f"{output_dir}/hyperparameter_heatmap.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"超参数热力图已保存到: {output_path}")
        
        # 找出最佳参数组合
        best_idx = np.argmax(mean_scores)
        best_c = c_values[best_idx]
        best_gamma = gamma_values[best_idx]
        best_score = mean_scores[best_idx]
        
        print(f"\n最佳超参数组合:")
        print(f"  C = {best_c}")
        print(f"  Gamma = {best_gamma}")
        print(f"  10折平均准确率 = {best_score:.4f} ({best_score*100:.2f}%)")
        
        
        return {
            'best_c': best_c,
            'best_gamma': best_gamma,
            'best_score': best_score,
            'unique_c': unique_c,
            'unique_gamma': unique_gamma,
            'heatmap_data': heatmap_data
        }
        
    except Exception as e:
        print(f"绘制超参数热力图时出错: {e}")
        import traceback
        traceback.print_exc()
        return None

def generate_svm_visualizations(metrics, output_dir="svm_analysis_plots"):
    """
    生成SVM分析的可视化图表
    
    参数:
    - metrics: 包含SVM分析的指标字典
    - output_dir: 输出目录
    """
    try:
        if 'svm_analysis' not in metrics:
            print("未找到SVM分析数据，无法生成可视化")
            return
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        svm_analysis = metrics['svm_analysis']
        
        # 设置中文字体和字体大小
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        plt.rcParams['font.size'] = 12
        plt.rcParams['axes.titlesize'] = 16
        plt.rcParams['axes.labelsize'] = 14
        plt.rcParams['xtick.labelsize'] = 12
        plt.rcParams['ytick.labelsize'] = 12
        plt.rcParams['legend.fontsize'] = 12
        
        # 1. 混淆矩阵热力图
        cm_info = svm_analysis.get('confusion_matrix', {})
        if cm_info and 'matrix' in cm_info:
            matrix = np.array(cm_info['matrix'])
            normalized_matrix = np.array(cm_info.get('normalized_matrix', matrix))
            
            # 获取类别标签（应该是1-5）
            unique_labels = sorted(svm_analysis.get('class_distribution', {}).get('true_labels', {}).keys())
            if not unique_labels:
                # 如果没有类别分布信息，从混淆矩阵大小推断
                unique_labels = list(range(1, matrix.shape[0] + 1))
            
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
            
            # 原始混淆矩阵
            sns.heatmap(matrix, annot=True, fmt='d', cmap='Blues', ax=ax1,
                       xticklabels=unique_labels, yticklabels=unique_labels,
                       annot_kws={'size': 14})
            ax1.set_title('混淆矩阵 (原始)', fontsize=18)
            ax1.set_xlabel('预测标签', fontsize=16)
            ax1.set_ylabel('真实标签', fontsize=16)
            
            # 标准化混淆矩阵
            sns.heatmap(normalized_matrix, annot=True, fmt='.3f', cmap='Blues', ax=ax2,
                       xticklabels=unique_labels, yticklabels=unique_labels,
                       annot_kws={'size': 14})
            ax2.set_title('混淆矩阵 (标准化)', fontsize=18)
            ax2.set_xlabel('预测标签', fontsize=16)
            ax2.set_ylabel('真实标签', fontsize=16)
            
            plt.tight_layout()
            plt.savefig(f"{output_dir}/confusion_matrix.png", dpi=300, bbox_inches='tight')
            plt.close()
            print(f"混淆矩阵图已保存到: {output_dir}/confusion_matrix.png")
        
        # 2. 每折性能对比图
        fold_analysis = svm_analysis.get('fold_analysis', [])
        if fold_analysis:
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
            
            folds = [fold['fold'] for fold in fold_analysis]
            accuracies = [fold['accuracy'] for fold in fold_analysis]
            precisions = [fold['precision'] for fold in fold_analysis]
            recalls = [fold['recall'] for fold in fold_analysis]
            f1s = [fold['f1'] for fold in fold_analysis]
            
            # 计算所有指标的范围，用于设置合适的y轴范围
            all_values = accuracies + precisions + recalls + f1s
            min_val = min(all_values)
            max_val = max(all_values)
            # 添加一些边距，让图表更美观
            margin = (max_val - min_val) * 0.1
            y_min = max(0, min_val - margin)
            y_max = min(1, max_val + margin)
            
            # 准确率
            ax1.plot(folds, accuracies, 'o-', linewidth=2, markersize=8)
            ax1.set_title('每折准确率', fontsize=18)
            ax1.set_xlabel('折数', fontsize=16)
            ax1.set_ylabel('准确率', fontsize=16)
            ax1.grid(True, alpha=0.3)
            ax1.set_ylim(y_min, y_max)
            
            # 精确率
            ax2.plot(folds, precisions, 'o-', linewidth=2, markersize=8, color='orange')
            ax2.set_title('每折精确率', fontsize=18)
            ax2.set_xlabel('折数', fontsize=16)
            ax2.set_ylabel('精确率', fontsize=16)
            ax2.grid(True, alpha=0.3)
            ax2.set_ylim(y_min, y_max)
            
            # 召回率
            ax3.plot(folds, recalls, 'o-', linewidth=2, markersize=8, color='green')
            ax3.set_title('每折召回率', fontsize=18)
            ax3.set_xlabel('折数', fontsize=16)
            ax3.set_ylabel('召回率', fontsize=16)
            ax3.grid(True, alpha=0.3)
            ax3.set_ylim(y_min, y_max)
            
            # F1分数
            ax4.plot(folds, f1s, 'o-', linewidth=2, markersize=8, color='red')
            ax4.set_title('每折F1分数', fontsize=18)
            ax4.set_xlabel('折数', fontsize=16)
            ax4.set_ylabel('F1分数', fontsize=16)
            ax4.grid(True, alpha=0.3)
            ax4.set_ylim(y_min, y_max)
            
            plt.tight_layout()
            plt.savefig(f"{output_dir}/fold_performance.png", dpi=300, bbox_inches='tight')
            plt.close()
            print(f"每折性能图已保存到: {output_dir}/fold_performance.png")
        
        print(f"\n所有可视化图表已保存到目录: {output_dir}")
        
    except Exception as e:
        print(f"生成可视化图表时出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"脚本运行出错: {e}")
        import traceback
        traceback.print_exc()
