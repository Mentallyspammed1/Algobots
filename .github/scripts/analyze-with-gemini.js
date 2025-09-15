#!/usr/bin/env node
const { GoogleGenerativeAI } = require(' @google/generative-ai');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);

const args = process.argv.slice(2);
const issues = args.find(a => a.startsWith('--issues='))?.split('=')[1] || '';
const fileList = args.find(a => a.startsWith('--files='))?.split('=') || '';
const files = fileList.split(/s+/).filter(Boolean);
const outputFile = args.find(a => a.startsWith('--output='))?.split('=') || 'analysis-results.json';

async function analyzeCode() {
  const analysisResults = {
    timestamp: new Date().toISOString(),
    filesAnalyzed: files.length,
    issues: [],
    suggestedFixes: [],
    summary: '',
    autoFixApplied: false
  };

  for (const filePath of files) {
    try {
      const code = fs.readFileSync(filePath, 'utf8');
      const prompt = buildPrompt(code, filePath, issues);
      const result = await analyzeWithGemini(prompt);

      if (result.issues) {
        result.issues.forEach(issue => {
          issue.file = filePath;
        });
        analysisResults.issues.push(...result.issues);
      }

      if (result.suggestedFixes) {
        result.suggestedFixes.forEach(fix => {
          fix.file = filePath;
        });
        analysisResults.suggestedFixes.push(...result.suggestedFixes);
      }

      if (result.autoFix && result.fixedContent) {
        fs.writeFileSync(filePath, result.fixedContent);
        execSync(`git add "${filePath}"`);
        analysisResults.autoFixApplied = true;
      }
    } catch (err) {
      console.error(`Error analyzing ${filePath}:`, err.message);
    }
  }

  analysisResults.summary = generateSummary(analysisResults);
  fs.writeFileSync(outputFile, JSON.stringify(analysisResults, null, 2));

  if (process.env.GITHUB_OUTPUT) {
    fs.appendFileSync(process.env.GITHUB_OUTPUT, "has-fixes=" + (analysisResults.suggestedFixes.length > 0) + "\n");
    fs.appendFileSync(process.env.GITHUB_OUTPUT, "changes-summary=" + analysisResults.summary.replace(/\n/g, '%0A') + "\n");
    fs.appendFileSync(process.env.GITHUB_OUTPUT, "files-changed=" + analysisResults.suggestedFixes.map(f => f.file).join(', ') + "\n");
  }
}

function buildPrompt(code, filePath, issues) {
  return `
Analyze and return JSON only.

File: ${filePath}
Known Lint Issues: ${issues.substring(0, 800)}

Code:
```${getLanguage(filePath)}
${code.substring(0, 6000)}
```

Return JSON { issues, suggestedFixes, autoFix, fixedContent, summary }
`.trim();
}

async function analyzeWithGemini(prompt) {
  const model = genAI.getGenerativeModel({ model: 'gemini-1.5-flash' });
  let response;
  try {
    const result = await model.generateContent(prompt);
    response = result.response.text();
    return safeJSONParse(response);
  } catch {
    console.warn('First parse failed, retrying with stricter JSON request...');
    const retry = await model.generateContent(prompt + 'nReturn only valid JSON.');
    return safeJSONParse(retry.response.text()) || {};
  }
}

function safeJSONParse(text) {
  try {
    const jsonMatch = text.match(/{[sS]*}/);
    if (jsonMatch) return JSON.parse(jsonMatch[0]);
  } catch { return null; }
  return null;
}

function generateSummary(r) {
  const emojiMap = { low: "🟢", medium: "🟡", high: "🔴", critical: "🚨" };
  const severities = r.issues.reduce((acc, i) => {
    acc[i.severity] = (acc[i.severity] || 0) + 1;
    return acc;
  }, {});
  return `
### Analysis Summary
- Total Issues: ${r.issues.length}
- Fixes Suggested: ${r.suggestedFixes.length}
- Auto-fixes Applied: ${r.autoFixApplied ? "✅ Yes" : "❌ No"}
${Object.entries(severities).map(([sev, count]) => `${emojiMap[sev] || sev}: ${count}`).join('n')}
`;
}

function getLanguage(f) {
  if (f.endsWith('.ts') || f.endsWith('.tsx')) return 'typescript';
  if (f.endsWith('.js') || f.endsWith('.jsx')) return 'javascript';
  return 'text';
}

if (require.main === module) analyzeCode();