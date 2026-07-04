import { Fragment, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * Lightweight, dependency-free Markdown-ish renderer for FANI's chat replies.
 *
 * The model often returns lightly-formatted text (bold, bullet/numbered lists,
 * short headings, inline code, links). Rendering that as raw pre-wrapped text
 * shows literal `**` / `- ` characters, which looks unpolished. This parses the
 * common subset into clean React elements — no `dangerouslySetInnerHTML`, so
 * there's no XSS surface, and partial markdown (mid-stream) degrades to plain
 * text instead of breaking.
 */

// ── Inline formatting: **bold**, *italic*, `code`, [text](url) ──────────────────
const INLINE = /(`[^`]+`)|(\*\*[^*\n]+\*\*)|(__[^_\n]+__)|(\*[^*\n]+\*)|(_[^_\n]+_)|(\[[^\]\n]+\]\([^)\n]+\))/g

function renderInline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = []
  let last = 0
  let match: RegExpExecArray | null
  let i = 0
  INLINE.lastIndex = 0
  while ((match = INLINE.exec(text)) !== null) {
    if (match.index > last) nodes.push(text.slice(last, match.index))
    const tok = match[0]
    const key = `${keyBase}-${i++}`
    if (tok.startsWith('`')) {
      nodes.push(
        <code
          key={key}
          className="rounded bg-slate-100 dark:bg-white/10 px-1.5 py-0.5 text-[0.85em] font-mono text-brand-700 dark:text-brand-300"
        >
          {tok.slice(1, -1)}
        </code>,
      )
    } else if (tok.startsWith('**') || tok.startsWith('__')) {
      nodes.push(
        <strong key={key} className="font-semibold text-slate-900 dark:text-white">
          {tok.slice(2, -2)}
        </strong>,
      )
    } else if (tok.startsWith('[')) {
      const m = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok)
      if (m) {
        nodes.push(
          <a
            key={key}
            href={m[2]}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-brand-600 dark:text-brand-400 underline underline-offset-2 hover:text-brand-700 dark:hover:text-brand-300"
          >
            {m[1]}
          </a>,
        )
      } else {
        nodes.push(tok)
      }
    } else {
      nodes.push(
        <em key={key} className="italic">
          {tok.slice(1, -1)}
        </em>,
      )
    }
    last = INLINE.lastIndex
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

type Block =
  | { type: 'heading'; level: number; text: string }
  | { type: 'ul'; items: string[] }
  | { type: 'ol'; items: string[] }
  | { type: 'p'; lines: string[] }

function parseBlocks(src: string): Block[] {
  const lines = src.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '')
    const heading = /^(#{1,3})\s+(.*)$/.exec(line)
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line)
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line)
    const prev = blocks[blocks.length - 1]

    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2] })
    } else if (bullet) {
      if (prev?.type === 'ul') prev.items.push(bullet[1])
      else blocks.push({ type: 'ul', items: [bullet[1]] })
    } else if (numbered) {
      if (prev?.type === 'ol') prev.items.push(numbered[1])
      else blocks.push({ type: 'ol', items: [numbered[1]] })
    } else if (line.trim() === '') {
      // Blank line ends the current paragraph
      if (prev?.type === 'p') blocks.push({ type: 'p', lines: [] })
    } else {
      if (prev?.type === 'p') prev.lines.push(line)
      else blocks.push({ type: 'p', lines: [line] })
    }
  }
  return blocks.filter((b) => !(b.type === 'p' && b.lines.length === 0))
}

export default function FormattedMessage({
  content,
  className,
}: {
  content: string
  className?: string
}) {
  const blocks = parseBlocks(content)

  return (
    <div className={cn('space-y-2.5 text-sm leading-relaxed', className)}>
      {blocks.map((block, bi) => {
        if (block.type === 'heading') {
          return (
            <p
              key={bi}
              className={cn(
                'font-semibold text-slate-900 dark:text-white',
                block.level === 1 ? 'text-base' : 'text-sm',
              )}
            >
              {renderInline(block.text, `h-${bi}`)}
            </p>
          )
        }
        if (block.type === 'ul') {
          return (
            <ul key={bi} className="list-disc space-y-1 pl-5 marker:text-brand-400">
              {block.items.map((it, ii) => (
                <li key={ii}>{renderInline(it, `ul-${bi}-${ii}`)}</li>
              ))}
            </ul>
          )
        }
        if (block.type === 'ol') {
          return (
            <ol key={bi} className="list-decimal space-y-1 pl-5 marker:text-brand-400 marker:font-semibold">
              {block.items.map((it, ii) => (
                <li key={ii}>{renderInline(it, `ol-${bi}-${ii}`)}</li>
              ))}
            </ol>
          )
        }
        return (
          <p key={bi}>
            {block.lines.map((ln, li) => (
              <Fragment key={li}>
                {li > 0 && <br />}
                {renderInline(ln, `p-${bi}-${li}`)}
              </Fragment>
            ))}
          </p>
        )
      })}
    </div>
  )
}
