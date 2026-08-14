#!/usr/bin/env node
/**
 * discover-plugins.mjs — 自动发现 → 同步 → 发布 DSH 插件（全自动接管发布体系）
 *
 * 流程：
 *   1. 发现：搜索 GitHub 账号下所有 dsh 相关仓库（名字含 dsh / topic: dsh-plugin|dsh|deepseek-harness），
 *      读取每个仓库的 package.json（远程），提取包名、版本、dsh.bundle / dsh.client 声明、prepare / CI 状态。
 *   2. 对比：npm registry 上已发布版本 vs 仓库版本 → PENDING（未发布）/ PUBLISHED / OUTDATED（仓库领先，待发新版本）。
 *   3. 同步（--sync）：对缺失的本地 checkout 做 git clone，已存在的 git pull --ff-only。
 *   4. 发送（--auto-tag）：对未发布版本打 v<version> tag 并推送 → 触发该仓库 publish.yml
 *      （tag → 构建 → npm publish → GitHub Release），实现"自动发送到社区"。
 *
 * 用法：
 *   node scripts/discover-plugins.mjs             # 仅发现 + 状态报告（dry-run，默认不写任何远程）
 *   node scripts/discover-plugins.mjs --json      # 输出 JSON（也写入 plugins-inventory.json）
 *   node scripts/discover-plugins.mjs --sync      # 先同步本地 checkout 再报告
 *   node scripts/discover-plugins.mjs --sync --auto-tag   # 同步 + 对未发布版本打 tag 推送（触发 CI 发布）
 *   node scripts/discover-plugins.mjs --tag-version 0.1.0 # 与 --auto-tag 同用：用指定版本代替 package.json version
 *
 * 前置：gh CLI 已登录（gh auth status），npm 可访问 registry。
 * 安全：默认纯只读；--sync 只写本地；--auto-tag 才会推送 tag（触发各仓库发布流水线）。
 */

import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { homedir } from 'node:os'

const OWNER = process.env.DSH_PLUGIN_OWNER ?? ''
const CHECKOUT_ROOT = process.env.DSH_CHECKOUT_ROOT ?? join(homedir(), 'dsh-plugin-checkouts')
const INVENTORY_FILE = join(process.cwd(), 'plugins-inventory.json')

const args = process.argv.slice(2)
const SYNC = args.includes('--sync')
const AUTO_TAG = args.includes('--auto-tag')
const JSON_ONLY = args.includes('--json')
const TAG_VERSION = args.includes('--tag-version')
  ? args[args.indexOf('--tag-version') + 1]
  : null

function sh(cmd, cmdArgs, opts = {}) {
  try {
    const out = execFileSync(cmd, cmdArgs, {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
      ...opts,
    })
    return { ok: true, out: out.trim() }
  } catch (e) {
    return { ok: false, out: String(e.stderr ?? e.message).trim() }
  }
}

/** 搜索候选仓库（多种口径，去重）。 */
function searchRepos() {
  const found = new Map()
  const queries = [
    ['gh', ['search', 'repos', '--owner', OWNER, 'dsh', '--json', 'fullName', '--limit', '50']],
    ['gh', ['search', 'repos', '--owner', OWNER, '--topic', 'dsh-plugin', '--json', 'fullName', '--limit', '50']],
    ['gh', ['search', 'repos', '--owner', OWNER, '--topic', 'dsh', '--json', 'fullName', '--limit', '50']],
    ['gh', ['search', 'repos', '--owner', OWNER, '--topic', 'deepseek-harness', '--json', 'fullName', '--limit', '50']],
  ]
  for (const [cmd, cmdArgs] of queries) {
    const r = sh(cmd, cmdArgs)
    if (!r.ok) continue
    try {
      for (const item of JSON.parse(r.out)) {
        if (!found.has(item.fullName)) found.set(item.fullName, {})
      }
    } catch { /* skip */ }
  }
  return [...found.keys()].sort()
}

/** 读取远程 package.json（gh api，base64 解码）。 */
function fetchRemotePackage(repo) {
  const r = sh('gh', ['api', `repos/${repo}/contents/package.json`, '--jq', '.content'])
  if (!r.ok) return null
  try {
    return JSON.parse(Buffer.from(r.out, 'base64').toString('utf8'))
  } catch {
    return null
  }
}

/** 远程默认分支 HEAD（用于判断本地是否最新）。 */
function fetchRemoteHead(repo) {
  const r = sh('git', ['ls-remote', `https://github.com/${repo}.git`, 'HEAD'])
  if (!r.ok) return null
  return r.out.split(/\s+/)[0] ?? null
}

/** npm 已发布版本（未发布返回 null）。 */
function fetchNpmVersion(name) {
  const r = sh('npm', ['view', name, 'version'], { timeout: 30000 })
  if (!r.ok) return null
  return r.out.split('\n')[0]?.trim() ?? null
}

/** 比较两个 semver（简单字符串序即可，版本号均规范化）。 */
function cmp(a, b) {
  const pa = a.split('.').map(Number)
  const pb = b.split('.').map(Number)
  for (let i = 0; i < 3; i++) {
    if ((pa[i] ?? 0) !== (pb[i] ?? 0)) return (pa[i] ?? 0) - (pb[i] ?? 0)
  }
  return 0
}

function localCheckoutState(repo) {
  const dir = join(CHECKOUT_ROOT, repo.split('/')[1])
  if (!existsSync(dir)) return { exists: false, dir: null, head: null }
  const head = sh('git', ['-C', dir, 'rev-parse', 'HEAD']).out || null
  return { exists: true, dir, head }
}

async function syncCheckout(repo) {
  const name = repo.split('/')[1]
  const dir = join(CHECKOUT_ROOT, name)
  if (!existsSync(dir)) {
    console.log(`  clone ${repo} → ${dir}`)
    const r = sh('git', ['clone', `https://github.com/${repo}.git`, dir], { timeout: 120000 })
    return r.ok
  }
  console.log(`  pull ${repo}`)
  const r = sh('git', ['-C', dir, 'pull', '--ff-only'], { timeout: 120000 })
  return r.ok
}

async function main() {
  console.log(`[discover] owner=${OWNER} checkoutRoot=${CHECKOUT_ROOT}`)
  const repos = searchRepos()
  console.log(`[discover] found ${repos.length} candidate repos\n`)

  if (SYNC) {
    console.log('[sync] updating local checkouts…')
    for (const repo of repos) await syncCheckout(repo)
    console.log('')
  }

  const inventory = []
  for (const repo of repos) {
    const pkg = fetchRemotePackage(repo)
    if (!pkg?.name) continue
    const npmVersion = fetchNpmVersion(pkg.name)
    const version = pkg.version
    let status
    if (!npmVersion) status = 'PENDING'          // 从未发布
    else if (cmp(version, npmVersion) > 0) status = 'OUTDATED'  // 仓库领先，待发
    else if (cmp(version, npmVersion) === 0) status = 'PUBLISHED'
    else status = 'BEHIND'                        // 仓库落后于 npm（异常）

    const local = localCheckoutState(repo)
    const remoteHead = fetchRemoteHead(repo)
    const localFresh = local.exists && remoteHead ? local.head === remoteHead : null

    const entry = {
      repo,
      package: pkg.name,
      version,
      npmVersion,
      status,
      isBundle: Boolean(pkg.dsh?.bundle?.patch),
      hasClient: Boolean(pkg.dsh?.client),
      hasPrepare: Boolean(pkg.scripts?.prepare),
      hasCi: null,
      local: local.exists ? local.dir : null,
      localFresh,
    }
    if (local.exists) {
      entry.hasCi = existsSync(join(local.dir, '.github', 'workflows', 'publish.yml'))
    } else {
      const wf = sh('gh', ['api', `repos/${repo}/contents/.github/workflows/publish.yml`, '--jq', '.name'])
      entry.hasCi = wf.ok
    }
    inventory.push(entry)
  }

  if (JSON_ONLY) {
    const doc = { generatedAt: new Date().toISOString(), owner: OWNER, plugins: inventory }
    await writeFile(INVENTORY_FILE, JSON.stringify(doc, null, 2))
    console.log(JSON.stringify(doc, null, 2))
    return
  }

  console.log('REPO | PKG | VERSION | NPM | STATUS | BUNDLE | CLIENT | PREPARE | CI | LOCAL-FRESH')
  console.log('-'.repeat(120))
  for (const e of inventory) {
    console.log(
      `${e.repo} | ${e.package} | ${e.version} | ${e.npmVersion ?? '—'} | ${e.status} | ` +
      `${e.isBundle ? '✓' : '✗'} | ${e.hasClient ? '✓' : '✗'} | ${e.hasPrepare ? '✓' : '✗'} | ` +
      `${e.hasCi ? '✓' : '✗'} | ${e.localFresh === null ? 'n/a' : e.localFresh ? '✓' : 'STALE'}`,
    )
  }

  const actionable = inventory.filter(e => (e.status === 'PENDING' || e.status === 'OUTDATED') && e.isBundle)
  console.log('\n[summary]')
  console.log(`  total=${inventory.length} pending/outdated(bundle)=${actionable.length}`)
  for (const e of actionable) {
    const extra = []
    if (!e.hasPrepare) extra.push('缺 prepare（git 直装会失败）')
    if (!e.hasCi) extra.push('缺 publish.yml（无法自动发布）')
    const localHint = e.localFresh === false ? '本地 STALE，先 --sync' : e.local ? `本地 ${e.local}` : '本地无 checkout，先 --sync'
    console.log(`  → ${e.package}@${e.version}（npm: ${e.npmVersion ?? '未发布'}）${extra.length ? '⚠ ' + extra.join('；') : ''}｜${localHint}`)
    if (extra.length === 0) {
      const tag = TAG_VERSION ?? e.version
      if (AUTO_TAG) {
        console.log(`    [auto-tag] git -C ${e.local} tag v${tag} && git -C ${e.local} push origin v${tag}`)
      } else {
        console.log(`    [建议] git -C ${e.local} tag v${tag} && git -C ${e.local} push origin v${tag}   # 触发 CI 发布`)
      }
    }
  }

  if (AUTO_TAG) {
    console.log('\n[auto-tag] executing…')
    for (const e of actionable) {
      if (!e.local || e.localFresh === false) {
        console.log(`  skip ${e.package}: 本地 checkout 缺失或非最新（先 --sync）`)
        continue
      }
      const tag = `v${TAG_VERSION ?? e.version}`
      const tagExists = sh('git', ['-C', e.local, 'tag', '-l', tag]).out.length > 0
      if (tagExists) {
        console.log(`  skip ${e.package}: tag ${tag} 已存在`)
        continue
      }
      const r1 = sh('git', ['-C', e.local, 'tag', tag])
      const r2 = sh('git', ['-C', e.local, 'push', 'origin', tag])
      console.log(`${r1.ok && r2.ok ? '  ✓' : '  ✗'} ${e.package}: tag ${tag} → push ${r2.ok ? 'ok' : 'failed'}（CI 将自动发布到 npm）`)
    }
  }

  const doc = { generatedAt: new Date().toISOString(), owner: OWNER, plugins: inventory }
  await writeFile(INVENTORY_FILE, JSON.stringify(doc, null, 2))
  console.log(`\n[inventory] written → ${INVENTORY_FILE}`)
}

await main()
