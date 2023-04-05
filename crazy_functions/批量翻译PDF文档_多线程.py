from toolbox import CatchException, report_execption, write_results_to_file, predict_no_ui_but_counting_down
import re
import unicodedata
fast_debug = False


def is_paragraph_break(match):
    """
    根据给定的匹配结果来判断换行符是否表示段落分隔。
    如果换行符前为句子结束标志（句号，感叹号，问号），且下一个字符为大写字母，则换行符更有可能表示段落分隔。
    也可以根据之前的内容长度来判断段落是否已经足够长。
    """
    prev_char, next_char = match.groups()

    # 句子结束标志
    sentence_endings = ".!?"

    # 设定一个最小段落长度阈值
    min_paragraph_length = 140

    if prev_char in sentence_endings and next_char.isupper() and len(match.string[:match.start(1)]) > min_paragraph_length:
        return "\n\n"
    else:
        return " "


def normalize_text(text):
    """
    通过把连字（ligatures）等文本特殊符号转换为其基本形式来对文本进行归一化处理。
    例如，将连字 "fi" 转换为 "f" 和 "i"。
    """
    # 对文本进行归一化处理，分解连字
    normalized_text = unicodedata.normalize("NFKD", text)

    # 替换其他特殊字符
    cleaned_text = re.sub(r'[^\x00-\x7F]+', '', normalized_text)

    return cleaned_text


def clean_text(raw_text):
    """
    对从 PDF 提取出的原始文本进行清洗和格式化处理。
    1. 对原始文本进行归一化处理。
    2. 替换跨行的连词，例如 “Espe-\ncially” 转换为 “Especially”。
    3. 根据 heuristic 规则判断换行符是否是段落分隔，并相应地进行替换。
    """
    # 对文本进行归一化处理
    normalized_text = normalize_text(raw_text)

    # 替换跨行的连词
    text = re.sub(r'(\w+-\n\w+)',
                  lambda m: m.group(1).replace('-\n', ''), normalized_text)

    # 根据前后相邻字符的特点，找到原文本中的换行符
    newlines = re.compile(r'(\S)\n(\S)')

    # 根据 heuristic 规则，用空格或段落分隔符替换原换行符
    final_text = re.sub(newlines, lambda m: m.group(
        1) + is_paragraph_break(m) + m.group(2), text)

    return final_text.strip()


def read_and_clean_pdf_text(fp):
    import fitz, re
    import numpy as np
    # file_content = ""
    with fitz.open(fp) as doc:
        meta_txt = []
        meta_font = []
        for page in doc:
            # file_content += page.get_text()
            text_areas = page.get_text("dict")  # 获取页面上的文本信息


            # # 行元提取                           for each word segment with in line             for each line                                   for each block
            # meta_txt.extend( [   ["".join(     [wtf['text'] for wtf in l['spans'] ])          for l in t['lines']   ]              for t in text_areas['blocks'] if 'lines' in t])
            # meta_font.extend([   [     np.mean([wtf['size'] for wtf in l['spans'] ])          for l in t['lines']   ]              for t in text_areas['blocks'] if 'lines' in t])

            # 块元提取                           for each word segment with in line             for each line                                   for each block
            meta_txt.extend( [   " ".join(["".join(     [wtf['text'] for wtf in l['spans'] ])          for l in t['lines']   ])              for t in text_areas['blocks'] if 'lines' in t])
            meta_font.extend([   np.mean( [     np.mean([wtf['size'] for wtf in l['spans'] ])          for l in t['lines']   ])              for t in text_areas['blocks'] if 'lines' in t])
        
        def 把字符太少的块清除为回车(meta_txt):
            for index, block_txt in enumerate(meta_txt):
                if len(block_txt) < 100:
                    meta_txt[index] = '\n'
            return meta_txt
        meta_txt = 把字符太少的块清除为回车(meta_txt)

        def 清理多余的空行(meta_txt):
            for index in reversed(range(1, len(meta_txt))):
                if meta_txt[index] == '\n' and meta_txt[index-1] == '\n':
                    meta_txt.pop(index)
            return meta_txt
        meta_txt = 清理多余的空行(meta_txt)

        def 合并小写开头的段落块(meta_txt):
            def starts_with_lowercase_word(s):
                pattern = r"^[a-z]+"
                match = re.match(pattern, s)
                if match:
                    return True
                else:
                    return False
            for _ in range(100):
                for index, block_txt in enumerate(meta_txt):
                    if starts_with_lowercase_word(block_txt):
                        if meta_txt[index-1]!='\n': meta_txt[index-1] += ' '
                        else: meta_txt[index-1] = ''
                        meta_txt[index-1] += meta_txt[index]
                        meta_txt[index] = '\n'
            return meta_txt
        meta_txt = 合并小写开头的段落块(meta_txt)
        meta_txt = 清理多余的空行(meta_txt)

        meta_txt = '\n'.join(meta_txt)
        # 清除重复的换行
        for _ in range(5):
            meta_txt = meta_txt.replace('\n\n','\n')

        # 换行 -> 双换行
        meta_txt = meta_txt.replace('\n', '\n\n')

        # print(meta_txt)

    return meta_txt

@CatchException
def 批量翻译PDF文档(txt, top_p, temperature, chatbot, history, systemPromptTxt, WEB_PORT):
    import glob
    import os

    # 基本信息：功能、贡献者
    chatbot.append([
        "函数插件功能？",
        "批量总结PDF文档。函数插件贡献者: Binary-Husky, ValeriaWong, Eralien"])
    yield chatbot, history, '正常'

    # 尝试导入依赖，如果缺少依赖，则给出安装建议
    try:
        import fitz, tiktoken
    except:
        report_execption(chatbot, history,
                         a=f"解析项目: {txt}",
                         b=f"导入软件依赖失败。使用该模块需要额外依赖，安装方法```pip install --upgrade pymupdf```。")
        yield chatbot, history, '正常'
        return

    # 清空历史，以免输入溢出
    history = []

    # 检测输入参数，如没有给定输入参数，直接退出
    if os.path.exists(txt):
        project_folder = txt
    else:
        if txt == "":
            txt = '空空如也的输入栏'
        report_execption(chatbot, history,
                         a=f"解析项目: {txt}", b=f"找不到本地项目或无权访问: {txt}")
        yield chatbot, history, '正常'
        return

    # 搜索需要处理的文件清单
    file_manifest = [f for f in glob.glob(
        f'{project_folder}/**/*.pdf', recursive=True)]

    # 如果没找到任何文件
    if len(file_manifest) == 0:
        report_execption(chatbot, history,
                         a=f"解析项目: {txt}", b=f"找不到任何.tex或.pdf文件: {txt}")
        yield chatbot, history, '正常'
        return

    # 开始正式执行任务
    yield from 解析PDF(file_manifest, project_folder, top_p, temperature, chatbot, history, systemPromptTxt)


def 解析PDF(file_manifest, project_folder, top_p, temperature, chatbot, history, systemPromptTxt):
    import time
    import glob
    import os
    import fitz
    import tiktoken
    from concurrent.futures import ThreadPoolExecutor
    print('begin analysis on:', file_manifest)
    for index, fp in enumerate(file_manifest):
        ### 1. 读取PDF文件
        file_content = read_and_clean_pdf_text(fp)
        ### 2. 递归地切割PDF文件
        from .crazy_utils import breakdown_txt_to_satisfy_token_limit_for_pdf
        enc = tiktoken.get_encoding("gpt2")
        TOKEN_LIMIT_PER_FRAGMENT = 2048
        get_token_num = lambda txt: len(enc.encode(txt))
        # 分解
        paper_fragments = breakdown_txt_to_satisfy_token_limit_for_pdf(
            txt=file_content, get_token_fn=get_token_num, limit=TOKEN_LIMIT_PER_FRAGMENT)
        print([get_token_num(frag) for frag in paper_fragments])
        ### 3. 逐个段落翻译
        ## 3.1. 多线程开始
        from request_llm.bridge_chatgpt import predict_no_ui_long_connection
        n_frag = len(paper_fragments)
        # 异步原子
        mutable = [["", time.time()] for _ in range(n_frag)]
        # 翻译函数
        def translate_(index, fragment, mutable):
            i_say = f"以下是你需要翻译的文章段落：{fragment}"
            # 请求gpt，需要一段时间
            gpt_say = predict_no_ui_long_connection(
                inputs=i_say, top_p=top_p, temperature=temperature, history=[], # ["请翻译：" if len(previous_result)!=0 else "", previous_result], 
                sys_prompt="请你作为一个学术翻译，负责将给定的文章段落翻译成中文，要求语言简洁、精准、凝练。你只需要给出翻译后的文本，不能重复原文。",
                observe_window=mutable[index])
            return gpt_say
        ### 4. 异步任务开始
        executor = ThreadPoolExecutor(max_workers=16)
        # Submit tasks to the pool
        futures = [executor.submit(translate_, index, frag, mutable) for index, frag in enumerate(paper_fragments)]
    
        ### 5. UI主线程，在任务期间提供实时的前端显示
        cnt = 0
        while True:
            cnt += 1
            time.sleep(1)
            worker_done = [h.done() for h in futures]
            if all(worker_done): 
                executor.shutdown(); break
            # 更好的UI视觉效果
            observe_win = []
            # 每个线程都要喂狗（看门狗）
            for thread_index, _ in enumerate(worker_done): 
                mutable[thread_index][1] = time.time()
            # 在前端打印些好玩的东西
            for thread_index, _ in enumerate(worker_done): 
                print_something_really_funny = "[ ...`"+mutable[thread_index][0][-30:].replace('\n','').replace('```','...').replace(' ','.').replace('<br/>','.....').replace('$','.')+"`... ]"
                observe_win.append(print_something_really_funny)
            stat_str = ''.join([f'执行中: {obs}\n\n' if not done else '已完成\n\n' for done, obs in zip(worker_done, observe_win)])
            chatbot[-1] = [chatbot[-1][0], f'多线程操作已经开始，完成情况: \n\n{stat_str}' + ''.join(['.']*(cnt%10+1))]; msg = "正常"
            yield chatbot, history, msg

        # Wait for tasks to complete
        results = [future.result() for future in futures]

        print(results)
        # full_result += gpt_say
        
        # history.extend([fp, full_result])

    res = write_results_to_file(history)
    chatbot.append(("完成了吗？", res)); msg = "完成"
    yield chatbot, history, msg


# if __name__ == '__main__':
#     pro()
