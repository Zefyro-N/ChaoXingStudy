#!/usr/bin/env node
/**
 * 数学/公式类题目答题基准测试
 *
 * 目的：量化「脚本的答题链路」在两个层面的表现
 *   1) 模型答对率        —— 模型输出本身对不对（分析层面）
 *   2) 输出可被脚本消化率 —— 输出是否符合 resolver 需要（格式层面）
 *
 * 用法（密钥只从环境变量读，不写文件、不进日志）：
 *   $env:DEEPSEEK_API_KEY = "sk-..."      # 你的新 Key
 *   node tools/math-bench.mjs                    # 三种提示词对比
 *   node tools/math-bench.mjs --garble-options    # 模拟页面公式选项提取失败
 *   node tools/math-bench.mjs --only A,B          # 只跑指定变体
 *
 * 题目与标准答案：tools/math-bench-questions.json（10 道线性代数，答案人工核算）
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const QFILE = path.join(HERE, 'math-bench-questions.json');
const API = 'https://api.deepseek.com/chat/completions';
const MODEL = 'deepseek-flash';

// ---------------------------------------------------------------- 提示词变体
/** O：**旧版**提示词（输出选项全文）—— 用于对比，已不再使用 */
const PROMPT_OLD = [
	'你是一个只负责给出答案的答题助手，服务对象是参加在线课程测验的学生。',
	'严格遵守以下规则：',
	'1. 只输出最终答案本身，不要输出解释、推理过程、题号、引号或其他任何前后缀。',
	'2. 单选题：输出正确选项的完整文字。若正确选项本身就是图片（选项写成 [图片N]），则改为输出该选项的图片标记，例如 [图片2]。',
	'3. 多选题：输出所有正确选项的完整文字，用英文逗号分隔；若选项是图片，则输出对应的图片标记，例如 [图片2],[图片4]。',
	'4. 判断题：只输出「正确」或「错误」两个词中的一个。',
	'5. 填空题：只输出答案文本。',
	'6. 不确定时给出你认为最可能的一个答案，不要提问、不要要求补充信息、不要拒绝作答。',
	'10. 涉及数学的内容一律写成纯文本：使用 Unicode 符号（∫ ∑ √ ≤ ≥ ≠ ± × ÷ ∞ ² ³ ₁ ₂ α β γ θ），上下标写成 x^2、a_n；禁止使用 LaTeX 语法。'
].join('\n');

/** A：**当前发货**提示词（与 cx-model.ts 逐字一致，选择题只输出字母） */
const PROMPT_A = [
	'你是一个只负责给出答案的答题助手，服务对象是参加在线课程测验的学生。',
	'严格遵守以下规则：',
	'1. 只输出最终答案本身。**不要输出任何前缀或后缀**（不要写「答案：」「选」「应该选」「故」「所以」），不要解释、不要推理过程、不要题号、不要引号。',
	'2. 单选题：**只输出选项字母**（A/B/C/D 中的一个）。不要输出选项文字；即使选项是公式或图片（写成 [图片N]），也只输出字母。',
	'3. 多选题：**只输出选项字母**，按字母顺序、用英文逗号分隔，例如 A,C。不要输出选项文字。',
	'4. 判断题：只输出「正确」或「错误」两个词之一，**不要加句号、不要补充说明**。',
	'5. 填空题：只输出答案文本。',
	'6. 不确定时给出你认为最可能的一个答案，不要提问、不要要求补充信息、不要拒绝作答。',
	'7. 题干或选项中的图片会写成 [图片N] 占位符，图片按 N 的顺序（[图片1]、[图片2]…）附在消息末尾，编号与占位符一一对应，请结合图片内容作答。',
	'8. 主观题（简答/名词解释/论述/计算）：给出可直接粘贴使用的完整答案。用「1. 2. 3.」或短横线分点作答；论述题要写出论点与理由，不要只给一句话。',
	'9. 【多空题】若题干中有两个及以上的空（题干里出现多个 ___ 或「第N空」），必须**按空逐个换行**输出，每行严格写成「第N空：答案」，编号从 1 开始、连续、每个空都写。',
	'10. 涉及数学的内容一律写成纯文本：使用 Unicode 符号（∫ ∑ √ ≤ ≥ ≠ ± × ÷ ∞ ² ³ ₁ ₂ α β γ θ），上下标写成 x^2、a_n；禁止使用 LaTeX 语法。'
].join('\n');

/** B：只输出字母（与 A 同义的精简版，用于交叉验证） */
const PROMPT_B = [
	'你是一个严谨的解题助手。请在心里完成推导，但不要输出推导过程。',
	'输出规则：',
	'1. 单选题：只输出正确选项的字母（例如 A）。信息不足以确定时，仍给出你认为最可能的字母。',
	'2. 多选题：按字母顺序用英文逗号输出，例如 A,C。',
	'3. 判断题：只输出「正确」或「错误」，不要标点、不要补充说明。',
	'4. 填空题：只输出答案本身；多空用中文分号「；」分隔，不要换行。',
	'5. 不要输出任何解释、题号、引号、前后缀；禁止 LaTeX，数学用纯文本（如 x^2、a_n、k(1,1,1)^T）。'
].join('\n');

/** C：允许先输出简短推理，再给最终答案行（测试"允许思考"是否提升正确率） */
const PROMPT_C = [
	'你是一个严谨的解题助手。',
	'先简要写出关键推导（不超过 80 字），然后另起一行输出：答案：<最终答案>',
	'最终答案要求：选择题只写字母（多选按字母顺序英文逗号分隔，如 A,C）；判断题只写「正确」或「错误」；填空只写数值/表达式。',
	'禁止 LaTeX，数学用纯文本（如 x^2、a_n、k(1,1,1)^T）。'
].join('\n');

const VARIANTS = {
	O: { name: 'O 旧版提示词（输出选项全文）', system: PROMPT_OLD },
	A: { name: 'A 当前发货提示词（只输出字母）', system: PROMPT_A },
	B: { name: 'B 输出字母（格式收紧）', system: PROMPT_B },
	C: { name: 'C 允许简短推导 + 答案行', system: PROMPT_C }
};

// ---------------------------------------------------------------- 工具
const LETTER = 'ABCDEFGH';

function parseArgs() {
	const a = process.argv.slice(2);
	const out = { garble: false, only: null, verbose: false };
	for (let i = 0; i < a.length; i++) {
		if (a[i] === '--garble-options') out.garble = true;
		else if (a[i] === '--only') out.only = (a[++i] || '').split(',').map((s) => s.trim().toUpperCase());
		else if (a[i] === '--verbose') out.verbose = true;
	}
	return out;
}

/** 模拟真实页面里"数学选项提取失败"：把公式型选项替换成残缺文本 */
function garbleOptions(options) {
	return options.map((o) => {
		const hasMath = /[\\^_(){}=+\-]|α|β|k\(|A/.test(o);
		if (!hasMath) return o;
		// 只保留少量可识别片段 + 占位，模拟 MathJax/图片选项被提取成残片
		const frag = o.replace(/[\u4e00-\u9fa5]/g, '').replace(/\s+/g, ' ').trim();
		return frag.length > 3 ? frag.slice(0, 12) + '…' : '(公式选项，未能提取)';
	});
}

/** 从模型输出里抽取"选中的字母" */
function extractLetters(text) {
	const t = String(text || '');
	// 优先取"答案："之后的片段
	const idx = Math.max(t.lastIndexOf('答案：'), t.lastIndexOf('答案:'));
	const seg = idx >= 0 ? t.slice(idx + 3) : t;
	const up = seg.toUpperCase();
	// 形如 A / A,C / A、C / (A) / 选A
	const letters = [];
	const re = /(?<![A-Z])([A-H])(?![A-Z])/g;
	let m;
	while ((m = re.exec(up))) {
		if (!letters.includes(m[1])) letters.push(m[1]);
		if (letters.length >= 6) break;
	}
	return letters.sort();
}

function judge(found, expected) {
	const exp = expected.toUpperCase().split('').sort();
	return exp.length === found.length && exp.every((c, i) => c === found[i]);
}

/** A 变体输出的是选项全文，需要映射回字母（模拟 resolver 的匹配过程） */
function lettersFromFullText(text, options) {
	const t = String(text || '');
	const up = t.toUpperCase();
	const hits = [];
	options.forEach((opt, i) => {
		const norm = (s) => s.replace(/\s+/g, '').toUpperCase();
		const body = opt.replace(/^[A-H][.、．]\s*/, '');
		if (t.includes(opt) || (body.length > 2 && t.includes(body))) hits.push(LETTER[i]);
		// 兜底：输出里出现 "A." 这类字母标记
		if (new RegExp(`(^|[^A-Z])${LETTER[i]}([.、．)）]|$)`).test(up) && !hits.includes(LETTER[i])) hits.push(LETTER[i]);
	});
	return [...new Set(hits)].sort();
}

async function ask(system, user, key) {
	const body = {
		model: MODEL,
		messages: [
			{ role: 'system', content: system },
			{ role: 'user', content: user }
		],
		max_tokens: 8192,
		temperature: 0
	};
	const t0 = Date.now();
	const res = await fetch(API, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key },
		body: JSON.stringify(body)
	});
	const text = await res.text();
	let json = null;
	try {
		json = JSON.parse(text);
	} catch (e) {
		/* ignore */
	}
	if (!res.ok) throw new Error(`HTTP ${res.status}: ${text.slice(0, 300)}`);
	const msg = json?.choices?.[0]?.message || {};
	return {
		content: String(msg.content || '').trim(),
		reasoningLen: String(msg.reasoning_content || '').length,
		finish: json?.choices?.[0]?.finish_reason,
		ms: Date.now() - t0
	};
}

function buildUser(q, options) {
	const lines = [`题型：${q.type}`, `题干：${q.stem}`, '', '选项：'];
	options.forEach((o, i) => lines.push(`${LETTER[i]}. ${o}`));
	lines.push('', '请给出答案。');
	return lines.join('\n');
}

// ---------------------------------------------------------------- 主流程
async function main() {
	const args = parseArgs();
	const key = process.env.DEEPSEEK_API_KEY || '';
	if (!key) {
		console.error('缺少 DEEPSEEK_API_KEY 环境变量。');
		console.error('用法：$env:DEEPSEEK_API_KEY = "sk-..."; node tools/math-bench.mjs');
		process.exit(2);
	}

	const questions = JSON.parse(fs.readFileSync(QFILE, 'utf8'));
	const ids = args.only ? Object.keys(VARIANTS).filter((k) => args.only.includes(k)) : Object.keys(VARIANTS);

	console.log(`题目数：${questions.length}｜模型：${MODEL}｜选项扰动：${args.garble ? '是（模拟公式选项提取失败）' : '否'}`);
	console.log('');

	const summary = {};

	for (const vid of ids) {
		const v = VARIANTS[vid];
		let correct = 0;
		let bareLetter = 0;
		let failedCall = 0;
		const rows = [];

		for (const q of questions) {
			const options = args.garble ? garbleOptions(q.options) : q.options;
			let r = null;
			let found = [];
			try {
				r = await ask(v.system, buildUser(q, options), key);
				found =
					vid === 'O'
						? lettersFromFullText(r.content, options)
						: extractLetters(r.content);
				if (!found.length && vid === 'O') {
					// O 变体也允许 ABCD 兜底（脚本 resolver 里就存在这条兜底）
					found = extractLetters(r.content);
				}
			} catch (e) {
				failedCall++;
				rows.push({ q: q.id, ok: false, got: '(请求失败)', ms: 0, out: String(e.message).slice(0, 80) });
				continue;
			}
			const ok = judge(found, q.answer);
			if (ok) correct++;
			// 输出是否"只含字母"（最容易被 resolver 消化）
			if (/^[A-H]([,，、\s]*[A-H])*$/.test(r.content.trim().toUpperCase())) bareLetter++;
			rows.push({
				q: q.id,
				ok,
				got: found.join('') || '(未识别)',
				want: q.answer,
				ms: r.ms,
				reasonLen: r.reasoningLen,
				finish: r.finish,
				out: r.content.replace(/\s+/g, ' ').slice(0, 60)
			});
		}

		const answered = questions.length - failedCall;
		console.log(`=== ${v.name} ===`);
		for (const row of rows) {
			const mark = row.ok ? '✅' : '❌';
			console.log(
				`  ${mark} Q${String(row.q).padStart(2)} 期望 ${row.want ?? '?'} 得到 ${String(row.got).padEnd(4)} ` +
					`(${row.ms}ms${row.finish ? ' ' + row.finish : ''}${row.reasonLen ? ' reasoning=' + row.reasonLen : ''})` +
					(row.ok ? '' : `  ← 模型输出: ${row.out}`)
			);
		}
		const acc = answered ? correct / answered : 0;
		console.log(
			`  ▶ 答对 ${correct}/${answered}（${(acc * 100).toFixed(0)}%）` +
				`｜输出纯字母 ${bareLetter}/${answered}｜请求失败 ${failedCall}`
		);
		console.log('');
		summary[vid] = { correct, answered, acc, bareLetter, failedCall };
	}

	console.log('=== 汇总 ===');
	for (const vid of ids) {
		const s = summary[vid];
		console.log(
			`  ${VARIANTS[vid].name.padEnd(28)} 答对率 ${(s.acc * 100).toFixed(0)}%  ` +
				`纯字母输出 ${s.bareLetter}/${s.answered}  失败 ${s.failedCall}`
		);
	}
}

main().catch((e) => {
	console.error('运行失败：', e);
	process.exit(1);
});
