/**
 * Flattens the model's markdown into plain prose for display.
 *
 * The report generator is not asked for markdown, it just tends to produce it, so the
 * stored summary keeps whatever came back and this strips the syntax at render time.
 * Structure is preserved rather than discarded: headings and list items stay on their
 * own lines, only the decoration goes.
 */
export function toPlainText(md: string | null | undefined): string {
  if (!md) return ""

  return (
    md
      // fenced and inline code keep their contents, lose their ticks
      .replace(/```[a-z]*\n?([\s\S]*?)```/gi, "$1")
      .replace(/`([^`]+)`/g, "$1")
      // links and images become their label
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      // emphasis markers, longest first so ** is not left behind by *
      .replace(/\*\*\*([^*]+)\*\*\*/g, "$1")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1$2")
      .replace(/__([^_]+)__/g, "$1")
      .replace(/~~([^~]+)~~/g, "$1")
      // horizontal rules carry no meaning once the styling is gone
      .replace(/^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$/gm, "")
      // heading and blockquote markers
      .replace(/^[ \t]{0,3}#{1,6}[ \t]+/gm, "")
      .replace(/^[ \t]{0,3}>[ \t]?/gm, "")
      // bullets become a real bullet character; numbered lists keep their numbers
      .replace(/^[ \t]*[-*+][ \t]+/gm, "• ")
      // markdown's two-space line break is invisible once rendered as text
      .replace(/[ \t]+$/gm, "")
      // collapse the runs of blank lines those removals leave behind
      .replace(/\n{3,}/g, "\n\n")
      .trim()
  )
}
