"""Word version of the Paper 1 manuscript (for language checks and co-authors who prefer Word).

    uv run --with pypandoc-binary python scripts/paper_docx.py [--out papers/paper1/main.docx]

The LaTeX manuscript stays the source of truth. This script flattens it for pandoc: inlines the
section and generated table files, replaces every generated number macro by its value
(papers/paper1/generated/numbers.tex), renders the pgfplots figures to PNG with tectonic and
pdftoppm, drops drafting notes and the Wiley class's front-matter commands, and converts with
pandoc (citations resolved from refs.bib by citeproc). pypandoc-binary is used only through
`uv run --with`; it is not a project dependency.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

PAPER = Path(__file__).resolve().parents[1] / "papers" / "paper1"


def read_macros() -> dict[str, str]:
    """\\newcommand{\\Name}{value} from numbers.tex and the figure legends."""
    out: dict[str, str] = {}
    for f in (PAPER / "generated" / "numbers.tex", PAPER / "sections" / "00_legends.tex"):
        text = f.read_text()
        i = 0
        while (m := re.compile(r"\\newcommand\{\\([A-Za-z]+)\}\{").search(text, i)) is not None:
            j, depth = m.end(), 1
            while depth:
                depth += {"{": 1, "}": -1}.get(text[j], 0)
                j += 1
            out[m.group(1)] = text[m.end() : j - 1]
            i = j
    return out


def drop_ensuremath(s: str) -> str:
    """Numbers are plain text in Word; this also works where a macro sits inside $...$."""
    return re.sub(r"\\ensuremath\{((?:[^{}]|\{[^{}]*\})*)\}", r"\1", s)


def strip_command(s: str, name: str, keep_arg: bool = False, opt: bool = True) -> str:
    """Remove \\name[opt]{arg} (balanced braces), or keep only its argument."""
    pat = re.compile(r"\\" + name + (r"(\[[^\]]*\])?" if opt else "") + r"\{")
    while (m := pat.search(s)) is not None:
        j, depth = m.end(), 1
        while depth:
            depth += {"{": 1, "}": -1}.get(s[j], 0)
            j += 1
        s = s[: m.start()] + (s[m.end() : j - 1] if keep_arg else "") + s[j:]
    return s


def inline(text: str, figdir: Path) -> str:
    def repl_input(m: re.Match) -> str:
        name = m.group(1)
        p = PAPER / (name if name.endswith(".tex") else name + ".tex")
        return inline(p.read_text(), figdir) if p.exists() else ""

    def repl_gen(m: re.Match) -> str:
        name = m.group(1)
        if name.startswith("fig_"):
            return rf"\includegraphics{{{figdir / (name + '.png')}}}"
        p = PAPER / "generated" / f"{name}.tex"
        return p.read_text() if p.exists() else f"[{name}]"

    text = re.sub(
        r"\\IfFileExists\{generated/(fig_[a-z_]+)\.tex\}\{[^\n]*",
        lambda m: rf"\includegraphics{{{figdir / (m.group(1) + '.png')}}}",
        text,
    )
    text = re.sub(r"\\(?:gentable|genfile)\{([a-z0-9_]+)\}", repl_gen, text)
    text = re.sub(r"\\input\{([^}]+)\}", repl_input, text)
    return text


def render_figures(figdir: Path) -> None:
    for fig in sorted((PAPER / "generated").glob("fig_*.tex")):
        doc = figdir / f"{fig.stem}.tex"
        doc.write_text(
            "\\documentclass[border=4pt]{standalone}\n\\usepackage{pgfplots}\n"
            "\\pgfplotsset{compat=1.18}\n\\begin{document}\n\\begin{minipage}{15cm}\n"
            + fig.read_text()  # \\linewidth is the minipage width
            + "\\end{minipage}\n\\end{document}\n"
        )
        subprocess.run(["tectonic", doc.name], cwd=figdir, check=True, capture_output=True)
        subprocess.run(
            ["pdftoppm", "-r", "200", "-png", "-singlefile", f"{fig.stem}.pdf", fig.stem],
            cwd=figdir,
            check=True,
        )


def flatten(figdir: Path) -> str:
    macros = read_macros()
    main = (PAPER / "main.tex").read_text()
    body = main[
        main.index("\\begin{document}") + len("\\begin{document}") : main.index("\\end{document}")
    ]
    body = inline(body, figdir)
    body = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("%"))
    # front matter of the Wiley class -> plain text
    title = re.search(r"\\title\{(.*?)\}\n\\author", body, re.S).group(1).replace("\n", " ")
    abstract = re.search(r"\\abstract\[ABSTRACT\]\{(.*?)\}\n\n\\maketitle", body, re.S).group(1)
    keywords = re.search(r"\\keywords\{(.*?)\}\n", body, re.S).group(1).replace(" |", ";")
    front = (
        "Thai Hung Luu (Independent Researcher, Vinh Long, Vietnam; hung.luu.research@gmail.com; "
        "ORCID 0009-0004-2909-3359) and Nhat Hao Pham Ngo (School of Trade and International "
        "Economics, National Economics University, Hanoi, Vietnam; nhathao.research@gmail.com; "
        "ORCID 0009-0000-1537-6041)\n\nRunning title: Forecasting trend reversals\n\n"
        f"\\section*{{Abstract}}\n{abstract}\n\n\\textbf{{Keywords:}} {keywords.strip()}\n\n"
    )
    body = front + body[body.index("\\maketitle") + len("\\maketitle") :]
    body = body.replace("\\linenumbers", "").replace("\\bmsection", "\\section")
    # cross-references: numbers from a LaTeX run of the manuscript (its .aux file)
    subprocess.run(
        ["tectonic", "-X", "compile", "--keep-intermediates", "--outdir", str(figdir), "main.tex"],
        cwd=PAPER,
        check=True,
        capture_output=True,
    )
    aux = (figdir / "main.aux").read_text()
    labels = dict(re.findall(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}", aux))
    body = re.sub(r"\\(?:eq)?ref\{([^}]+)\}", lambda m: labels.get(m.group(1), "??"), body)
    for cmd in ("todo", "plan", "label"):
        body = strip_command(body, cmd)
    body = re.sub(r"\\setlength\{[^}]*\}\{[^}]*\}", "", body)
    body = re.sub(r"\\(footnotesize|scriptsize|small|centering)\b", "", body)
    body = body.replace("\\relax ", "")
    body = re.sub(r"L\{([^{}]*(?:\{[^{}]*\})?[^{}]*)\}", r"p{\1}", body)  # ragged column type -> p
    body = strip_command(body, "adjustbox", keep_arg=False)  # leftovers only
    # generated numbers and legends
    body = re.sub(
        r"\\gen\{([A-Za-z]+)\}", lambda m: macros.get(m.group(1), f"[{m.group(1)}]"), body
    )
    for _ in range(2):
        body = re.sub(
            r"\\([A-Za-z]+)(\{\})?",
            lambda m: macros[m.group(1)] if m.group(1) in macros else m.group(0),
            body,
        )
    body = drop_ensuremath(body)
    return (
        "\\documentclass{article}\n\\usepackage{graphicx}\n"
        f"\\title{{{title}}}\n\\begin{{document}}\n\\maketitle\n{body}\n\\end{{document}}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PAPER / "main.docx"))
    args = ap.parse_args()
    import pypandoc

    with tempfile.TemporaryDirectory() as tmp:
        figdir = Path(tmp)
        render_figures(figdir)
        flat = figdir / "flat.tex"
        flat.write_text(flatten(figdir))
        pypandoc.convert_file(
            str(flat),
            "docx",
            outputfile=args.out,
            extra_args=[
                "--citeproc",
                f"--bibliography={PAPER / 'refs.bib'}",
                f"--csl={PAPER / 'apa.csl'}",  # APA 7 (CSL project, CC BY-SA 3.0)
                f"--resource-path={figdir}",
                "--metadata=link-citations:true",
            ],
        )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
