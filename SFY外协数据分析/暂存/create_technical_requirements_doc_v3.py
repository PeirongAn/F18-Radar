"""
创建开发人员侧技术需求规格说明文档
基于用户提供的框架和代码文件
重点说明技术原理和实现逻辑
"""

from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.shared import OxmlElement, qn
from docx.oxml.ns import qn as nsqn
from docx.shared import RGBColor
from datetime import datetime

def set_chinese_font(paragraph, font_name='Microsoft YaHei'):
    """设置段落的中文字体"""
    for run in paragraph.runs:
        run.font.name = font_name
        run._element.rPr.rFonts.set(nsqn('w:eastAsia'), font_name)

def add_chinese_paragraph(doc, text, level=None, font_name='Microsoft YaHei'):
    """添加中文段落并设置字体"""
    if level is not None:
        paragraph = doc.add_heading(text, level)
    else:
        paragraph = doc.add_paragraph(text)
    
    set_chinese_font(paragraph, font_name)
    return paragraph

def create_technical_requirements_document():
    """创建技术需求规格说明文档"""
    
    # 创建文档
    doc = Document()
    
    # 设置文档样式以支持中文
    doc.styles['Normal'].font.name = 'Microsoft YaHei'
    doc.styles['Normal']._element.rPr.rFonts.set(nsqn('w:eastAsia'), 'Microsoft YaHei')
    doc.styles['Normal'].font.size = Pt(12)
    
    # 设置文档标题
    title = add_chinese_paragraph(doc, '开发人员侧技术需求规格说明文档', level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # 添加文档信息
    add_chinese_paragraph(doc, f'文档版本: 1.0')
    add_chinese_paragraph(doc, f'创建日期: {datetime.now().strftime("%Y年%m月%d日")}')
    add_chinese_paragraph(doc, f'文档类型: 技术需求规格说明')
    add_chinese_paragraph(doc, '')
    
    # 添加目录
    add_chinese_paragraph(doc, '目录', level=1)
    add_chinese_paragraph(doc, '1. 数据特征提取用例')
    add_chinese_paragraph(doc, '2. 信任水平模型构建用例')
    add_chinese_paragraph(doc, '3. 结果统计分析用例')
    add_chinese_paragraph(doc, '')
    
    # 用例1：数据特征提取
    add_chinese_paragraph(doc, '1. 数据特征提取用例', level=1)
    
    add_chinese_paragraph(doc, '1.1 功能描述', level=2)
    add_chinese_paragraph(doc, '从多源异构数据中提取和构建用于机器学习模型训练的特征向量。通过数据融合、特征工程和数据增强技术，将原始行为数据转换为可量化的特征表示，为后续的信任水平预测模型提供高质量的训练数据。')
    
    add_chinese_paragraph(doc, '1.2 前置条件', level=2)
    add_chinese_paragraph(doc, '• 存在多源数据存储：行为数据、问卷数据、实验数据')
    add_chinese_paragraph(doc, '• 数据格式标准化：JSON格式的问卷和实验数据，数据库格式的行为数据')
    add_chinese_paragraph(doc, '• 数据完整性：每个被试包含完整的四类任务数据')
    add_chinese_paragraph(doc, '• 系统环境：Python 3.8+，pandas、numpy、sqlite3库')
    add_chinese_paragraph(doc, '• 数据预处理：原始数据已通过数据清洗和格式转换')
    
    add_chinese_paragraph(doc, '1.3 后置条件', level=2)
    add_chinese_paragraph(doc, '• 生成统一的数据存储，包含所有原始数据表')
    add_chinese_paragraph(doc, '• 生成信任数据表，包含标签和基础特征')
    add_chinese_paragraph(doc, '• 生成增强特征数据，包含20维特征向量')
    add_chinese_paragraph(doc, '• 所有数据表结构完整，数据质量符合机器学习要求')
    add_chinese_paragraph(doc, '• 特征向量维度统一，数据类型标准化')
    
    add_chinese_paragraph(doc, '1.4 主流程', level=2)
    add_chinese_paragraph(doc, '• 数据源扫描：遍历多个数据目录，识别不同格式的数据文件')
    add_chinese_paragraph(doc, '• 数据格式解析：解析JSON格式的问卷文件和实验数据，提取结构化信息')
    add_chinese_paragraph(doc, '• 数据关联：基于用户标识和实验设置建立不同数据源之间的关联关系')
    add_chinese_paragraph(doc, '• 数据合并：将多源数据合并到统一的数据存储中，建立完整的数据视图')
    add_chinese_paragraph(doc, '• 基础特征计算：基于时间数据计算AI控制时间比例，反映人机交互中的控制权分配')
    add_chinese_paragraph(doc, '• 交互特征计算：计算人类主导程度，量化人类在交互过程中的控制优势')
    add_chinese_paragraph(doc, '• 任务特定特征：根据不同任务类型采用不同的特征计算逻辑，提取任务相关的行为特征')
    add_chinese_paragraph(doc, '• 数据标准化：对重复计数等字段进行重新编号，确保数据的一致性和连续性')
    add_chinese_paragraph(doc, '• 组合采样：采用组合数学方法，从N个重复实验中选取M个样本的所有可能组合')
    add_chinese_paragraph(doc, '• 统计特征计算：计算均值、标准差、变异系数等描述性统计量，捕捉数据的分布特征')
    add_chinese_paragraph(doc, '• 信任特征计算：基于决策序列计算决策稳定性、信任演化等高级特征，反映信任的动态变化')
    add_chinese_paragraph(doc, '• 特征向量构建：将计算得到的特征组合成固定维度的特征向量，为机器学习模型提供输入')
    
    add_chinese_paragraph(doc, '1.5 副流程', level=2)
    add_chinese_paragraph(doc, '• 数据清洗：删除无用的系统字段，保留业务相关的数据列')
    add_chinese_paragraph(doc, '• 异常处理：处理缺失值和数据类型转换，确保数据的完整性和一致性')
    add_chinese_paragraph(doc, '• 数据过滤：根据业务规则过滤无效数据，提高数据质量')
    add_chinese_paragraph(doc, '• 数据验证：检查数据完整性和一致性，确保特征计算的正确性')
    add_chinese_paragraph(doc, '• 索引优化：创建数据库索引提高查询性能，支持大规模数据处理')
    
    add_chinese_paragraph(doc, '1.6 输入信息', level=2)
    add_chinese_paragraph(doc, '• 行为数据：包含传感器任务和威胁排序任务的统计数据')
    add_chinese_paragraph(doc, '• 问卷数据：包含7个问题的评分数据，反映用户的信任水平')
    add_chinese_paragraph(doc, '• 实验数据：包含武器发射和平台控制任务的实验数据')
    add_chinese_paragraph(doc, '• 被试信息：预定义的用户标识列表')
    add_chinese_paragraph(doc, '• 任务类型：四种不同类型的任务，每种任务有不同的特征计算逻辑')
    
    add_chinese_paragraph(doc, '1.7 输出信息', level=2)
    add_chinese_paragraph(doc, '• 统一数据存储：包含所有原始数据表的合并数据库')
    add_chinese_paragraph(doc, '• 信任数据表：包含用户标识、任务信息、难度等级、AI等级、音频设置、数据标签、重复计数、AI控制时间、人类控制时间、总时间、AI时间比例、人类主导程度、接受AI建议等字段')
    add_chinese_paragraph(doc, '• 增强特征数据：包含20个特征列的特征数据表')
    add_chinese_paragraph(doc, '• 特征向量：20维特征矩阵，包括基础特征、统计特征、信任特征')
    add_chinese_paragraph(doc, '• 目标变量：1-5分类标签，用于机器学习模型的训练')
    
    add_chinese_paragraph(doc, '1.8 规则与约束', level=2)
    add_chinese_paragraph(doc, '• 数据完整性：所有必需字段不能为空，缺失数据需要特殊处理')
    add_chinese_paragraph(doc, '• 数据一致性：重复计数必须连续编号，确保数据顺序正确')
    add_chinese_paragraph(doc, '• 特征计算规则：时间比例和主导程度的分母不能为0，需要特殊处理')
    add_chinese_paragraph(doc, '• 数据增强约束：每个实验设置必须包含足够数量的重复实验才能进行组合采样')
    add_chinese_paragraph(doc, '• 文件命名规范：输出文件必须包含时间戳，确保文件唯一性')
    add_chinese_paragraph(doc, '• 数据类型约束：所有数值特征必须为浮点类型，分类特征为整数类型')
    
    # 用例2：信任水平模型构建
    add_chinese_paragraph(doc, '2. 信任水平模型构建用例', level=1)
    
    add_chinese_paragraph(doc, '2.1 功能描述', level=2)
    add_chinese_paragraph(doc, '基于增强特征数据构建支持向量机分类模型，用于预测用户的信任水平。通过超参数优化和交叉验证技术，实现高精度的多分类预测，为信任评估提供可靠的机器学习模型。')
    
    add_chinese_paragraph(doc, '2.2 前置条件', level=2)
    add_chinese_paragraph(doc, '• 存在增强特征数据，包含20维特征向量')
    add_chinese_paragraph(doc, '• 特征数据已标准化处理，数据类型正确')
    add_chinese_paragraph(doc, '• 目标变量已定义，为1-5分类标签')
    add_chinese_paragraph(doc, '• 系统具备机器学习库支持')
    add_chinese_paragraph(doc, '• 系统具备数值计算和数据处理能力')
    add_chinese_paragraph(doc, '• 数据质量：特征矩阵无缺失值，目标变量平衡')
    
    add_chinese_paragraph(doc, '2.3 后置条件', level=2)
    add_chinese_paragraph(doc, '• 生成最优超参数配置文件')
    add_chinese_paragraph(doc, '• 生成交叉验证结果文件')
    add_chinese_paragraph(doc, '• 生成超参数搜索过程记录')
    add_chinese_paragraph(doc, '• 生成可视化结果图表')
    add_chinese_paragraph(doc, '• 模型性能指标：准确率、精确率、召回率、F1分数')
    
    add_chinese_paragraph(doc, '2.4 主流程', level=2)
    add_chinese_paragraph(doc, '• 从数据存储中加载多任务数据')
    add_chinese_paragraph(doc, '• 应用数据增强策略生成训练样本')
    add_chinese_paragraph(doc, '• 构建特征矩阵和目标变量')
    add_chinese_paragraph(doc, '• 数据质量检查和异常处理')
    add_chinese_paragraph(doc, '• 参数空间定义：定义正则化参数C、核函数参数gamma、核函数类型等搜索空间')
    add_chinese_paragraph(doc, '• 网格搜索：使用网格搜索算法进行穷举搜索，评估所有参数组合')
    add_chinese_paragraph(doc, '• 交叉验证：使用分层K折交叉验证评估模型性能，确保类别平衡')
    add_chinese_paragraph(doc, '• 最优参数选择：选择交叉验证准确率最高的参数组合')
    add_chinese_paragraph(doc, '• 使用最优参数训练支持向量机模型')
    add_chinese_paragraph(doc, '• 进行分层K折交叉验证')
    add_chinese_paragraph(doc, '• 记录每折的预测结果和真实标签')
    add_chinese_paragraph(doc, '• 计算整体性能指标')
    add_chinese_paragraph(doc, '• 保存最优参数到配置文件')
    add_chinese_paragraph(doc, '• 保存折级详细结果到数据文件')
    add_chinese_paragraph(doc, '• 生成性能可视化图表')
    add_chinese_paragraph(doc, '• 输出模型性能报告')
    
    add_chinese_paragraph(doc, '2.5 副流程', level=2)
    add_chinese_paragraph(doc, '• 特征标准化：使用标准化方法进行特征缩放，消除量纲影响')
    add_chinese_paragraph(doc, '• 数据平衡：使用分层采样确保类别平衡，避免模型偏向多数类')
    add_chinese_paragraph(doc, '• 随机种子：设置固定随机种子确保结果可重现')
    add_chinese_paragraph(doc, '• 并行处理：使用多核并行计算加速超参数搜索')
    add_chinese_paragraph(doc, '• 模型验证：通过交叉验证避免过拟合，提高模型泛化能力')
    
    add_chinese_paragraph(doc, '2.6 输入信息', level=2)
    add_chinese_paragraph(doc, '• 信任数据：包含多任务数据的信任数据表')
    add_chinese_paragraph(doc, '• 任务选择：四种不同类型的任务类型')
    add_chinese_paragraph(doc, '• 特征列：20个增强特征（均值、标准差、变异系数、信任特征）')
    add_chinese_paragraph(doc, '• 目标变量：1-5分类标签')
    add_chinese_paragraph(doc, '• 参数网格：正则化参数、核函数参数、核函数类型等搜索空间')
    
    add_chinese_paragraph(doc, '2.7 输出信息', level=2)
    add_chinese_paragraph(doc, '• 最优超参数配置：包含最佳参数组合的配置文件')
    add_chinese_paragraph(doc, '• 交叉验证详细结果：包含每折详细结果的数据文件')
    add_chinese_paragraph(doc, '• 超参数搜索过程记录：包含所有参数组合性能的搜索记录')
    add_chinese_paragraph(doc, '• 可视化结果图表：包含性能指标的可视化图表')
    add_chinese_paragraph(doc, '• 模型性能指标：准确率、精确率、召回率、F1分数等评估指标')
    
    add_chinese_paragraph(doc, '2.8 规则与约束', level=2)
    add_chinese_paragraph(doc, '• 参数范围：正则化参数和核函数参数在指定范围内搜索')
    add_chinese_paragraph(doc, '• 核函数：主要使用径向基函数核，适合处理非线性分类问题')
    add_chinese_paragraph(doc, '• 交叉验证：必须使用分层K折交叉验证确保类别平衡')
    add_chinese_paragraph(doc, '• 评估指标：主要使用准确率作为主要评估指标')
    add_chinese_paragraph(doc, '• 数据增强：每个实验设置生成固定数量的样本')
    add_chinese_paragraph(doc, '• 文件命名：所有输出文件必须包含时间戳')
    add_chinese_paragraph(doc, '• 随机性控制：设置固定随机种子确保结果可重现')
    
    # 用例3：结果统计分析
    add_chinese_paragraph(doc, '3. 结果统计分析用例', level=1)
    
    add_chinese_paragraph(doc, '3.1 功能描述', level=2)
    add_chinese_paragraph(doc, '对模型训练结果进行深度统计分析，计算关键性能指标，评估模型质量。通过多维度指标分析，全面评估模型的预测性能、稳定性和泛化能力，为模型优化提供数据支持。')
    
    add_chinese_paragraph(doc, '3.2 前置条件', level=2)
    add_chinese_paragraph(doc, '• 存在交叉验证结果文件')
    add_chinese_paragraph(doc, '• 文件包含完整的交叉验证结果数据')
    add_chinese_paragraph(doc, '• 系统具备数值计算能力')
    add_chinese_paragraph(doc, '• 系统具备JSON文件解析能力')
    add_chinese_paragraph(doc, '• 数据格式：包含预测结果、真实标签、各折准确率等字段')
    
    add_chinese_paragraph(doc, '3.3 后置条件', level=2)
    add_chinese_paragraph(doc, '• 生成计算结果文件')
    add_chinese_paragraph(doc, '• 控制台输出详细性能指标')
    add_chinese_paragraph(doc, '• 所有指标计算完成并保存')
    add_chinese_paragraph(doc, '• 提供模型性能评估报告')
    
    add_chinese_paragraph(doc, '3.4 主流程', level=2)
    add_chinese_paragraph(doc, '• 读取交叉验证结果文件')
    add_chinese_paragraph(doc, '• 提取预测结果和真实标签')
    add_chinese_paragraph(doc, '• 提取各折准确率数据')
    add_chinese_paragraph(doc, '• 数据格式验证和完整性检查')
    add_chinese_paragraph(doc, '• 计算模型跟踪性能：使用归一化均方根误差评估预测准确性')
    add_chinese_paragraph(doc, '• 计算模型分辨率：通过最高与最低准确率差值评估模型稳定性')
    add_chinese_paragraph(doc, '• 计算模型泛化性：通过平均准确率评估模型整体性能')
    add_chinese_paragraph(doc, '• 计算预测匹配度：统计预测值与真实标签的匹配数量和比例')
    add_chinese_paragraph(doc, '• 保存指标到数据文件')
    add_chinese_paragraph(doc, '• 输出控制台显示结果')
    add_chinese_paragraph(doc, '• 生成性能评估报告')
    
    add_chinese_paragraph(doc, '3.5 副流程', level=2)
    add_chinese_paragraph(doc, '• 数据验证：检查输入文件格式和内容完整性')
    add_chinese_paragraph(doc, '• 异常处理：处理缺失数据或格式错误')
    add_chinese_paragraph(doc, '• 结果验证：确保计算结果在合理范围内')
    add_chinese_paragraph(doc, '• 数值精度：所有计算结果保留指定精度')
    
    add_chinese_paragraph(doc, '3.6 输入信息', level=2)
    add_chinese_paragraph(doc, '• 交叉验证结果文件：包含以下字段')
    add_chinese_paragraph(doc, '  - 所有预测结果列表')
    add_chinese_paragraph(doc, '  - 所有真实标签列表')
    add_chinese_paragraph(doc, '  - 各折准确率列表')
    add_chinese_paragraph(doc, '  - 各折详细信息')
    add_chinese_paragraph(doc, '• 计算参数：RMSE归一化因子、精度要求等')
    
    add_chinese_paragraph(doc, '3.7 输出信息', level=2)
    add_chinese_paragraph(doc, '• 计算结果文件：包含以下指标')
    add_chinese_paragraph(doc, '  - 模型跟踪性能（归一化RMSE）')
    add_chinese_paragraph(doc, '  - 模型分辨率（准确率差）')
    add_chinese_paragraph(doc, '  - 模型泛化性（平均准确率）')
    add_chinese_paragraph(doc, '  - 预测匹配统计')
    add_chinese_paragraph(doc, '  - 详细结果数据')
    add_chinese_paragraph(doc, '  - 文件信息')
    add_chinese_paragraph(doc, '• 控制台输出：指标计算过程和结果')
    
    add_chinese_paragraph(doc, '3.8 规则与约束', level=2)
    add_chinese_paragraph(doc, '• RMSE计算：使用归一化公式消除量纲影响')
    add_chinese_paragraph(doc, '• 分辨率计算：通过最高与最低准确率差值评估稳定性')
    add_chinese_paragraph(doc, '• 泛化性计算：通过平均准确率评估整体性能')
    add_chinese_paragraph(doc, '• 数据范围：预测值和真实标签必须在指定范围内')
    add_chinese_paragraph(doc, '• 文件格式：输出必须为JSON格式，包含UTF-8编码')
    add_chinese_paragraph(doc, '• 数值精度：所有计算结果保留指定精度')
    add_chinese_paragraph(doc, '• 错误处理：对异常数据进行合理处理，避免计算错误')
    
    # 添加技术规范
    add_chinese_paragraph(doc, '技术规范', level=1)
    add_chinese_paragraph(doc, '• 开发语言：Python 3.8+')
    add_chinese_paragraph(doc, '• 主要依赖库：')
    add_chinese_paragraph(doc, '  - pandas: 数据处理和特征工程')
    add_chinese_paragraph(doc, '  - numpy: 数值计算和统计分析')
    add_chinese_paragraph(doc, '  - sqlite3: 数据库操作和存储')
    add_chinese_paragraph(doc, '  - scikit-learn: 机器学习算法和评估')
    add_chinese_paragraph(doc, '  - matplotlib: 数据可视化')
    add_chinese_paragraph(doc, '  - json: JSON文件处理')
    add_chinese_paragraph(doc, '• 数据库：SQLite 3.x')
    add_chinese_paragraph(doc, '• 文件格式：JSON, CSV, PNG')
    add_chinese_paragraph(doc, '• 编码格式：UTF-8')
    add_chinese_paragraph(doc, '• 性能要求：支持大规模数据处理，内存优化')
    
    # 保存文档
    filename = f"技术需求规格说明文档_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    doc.save(filename)
    print(f"技术需求规格说明文档已生成: {filename}")
    
    return filename

if __name__ == "__main__":
    create_technical_requirements_document()
