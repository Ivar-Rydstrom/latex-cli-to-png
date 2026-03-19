import argparse
import os
import shutil
import subprocess
import sys
import tempfile

TEX_TEMPLATE = r"""\documentclass{{article}}
\usepackage{{amsmath}}
\usepackage{{amssymb}}
\usepackage{{fix-cm}}
\usepackage[paperwidth=20in,paperheight=20in,margin=0.5in]{{geometry}}
\pagestyle{{empty}}
\begin{{document}}
\fontsize{{120}}{{144}}\selectfont
{content}
\end{{document}}
"""

MATH_ENV_MARKERS = (
    r"\begin{equation",
    r"\begin{align",
    r"\begin{gather",
    r"\begin{multline",
    r"\begin{flalign",
    r"\begin{math",
    r"\[",
    "$$",
    "$",
)


def _needs_math_wrap(latex_string):
    """Check if the string needs to be wrapped in math mode delimiters."""
    stripped = latex_string.strip()
    for marker in MATH_ENV_MARKERS:
        if stripped.startswith(marker):
            return False
    return True


def _has_command(cmd):
    return shutil.which(cmd) is not None


def _run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def _render_with_matplotlib(content, png_path):
    """Render using matplotlib mathtext. No system LaTeX needed.
    Returns True on success, False if matplotlib is unavailable or the
    expression uses unsupported LaTeX (e.g. multi-line environments).
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    # Normalise display-math delimiters: \[...\] -> $...$
    stripped = content.strip()
    if stripped.startswith(r"\[") and stripped.endswith(r"\]"):
        stripped = "$" + stripped[2:-2].strip() + "$"

    try:
        # Use Computer Modern fonts to match LaTeX's default appearance
        plt.rcParams["mathtext.fontset"] = "cm"
        plt.rcParams["font.family"] = "serif"

        fig = plt.figure(figsize=(0.1, 0.1))
        fig.patch.set_facecolor("white")
        # Centre the text so bbox_inches='tight' captures the full glyph height
        fig.text(0.5, 0.5, stripped, fontsize=72, color="black",
                 ha="center", va="center")
        fig.savefig(png_path, dpi=300, bbox_inches="tight",
                    facecolor="white", pad_inches=0.15)
        plt.close(fig)
        return True
    except Exception:
        plt.close("all")
        return False


def _fitz_pdf_to_png(pdf_path, png_path):
    """Render PDF to tightly-cropped PNG using pymupdf (fitz)."""
    import fitz
    doc = fitz.open(pdf_path)
    page = doc[0]
    bbox_log = page.get_bboxlog()
    if bbox_log:
        content_rect = fitz.Rect()
        for _, r in bbox_log:
            content_rect |= fitz.Rect(r)
        pad = 4  # points
        clip = fitz.Rect(
            content_rect.x0 - pad, content_rect.y0 - pad,
            content_rect.x1 + pad, content_rect.y1 + pad,
        ) & page.rect
    else:
        clip = page.rect
    page.get_pixmap(dpi=600, clip=clip).save(png_path)


def _compile_and_convert(tmpdir):
    """Try LaTeX-based backends to produce a PNG. Returns path to PNG."""
    # Strategy 1: tectonic + pymupdf
    if _has_command("tectonic"):
        try:
            import fitz  # noqa: F401 — just checking availability
            result = _run(["tectonic", "input.tex"], cwd=tmpdir)
            if result.returncode != 0:
                print("Tectonic compilation failed:", file=sys.stderr)
                print(result.stdout, file=sys.stderr)
                sys.exit(1)
            png_path = os.path.join(tmpdir, "input.png")
            _fitz_pdf_to_png(os.path.join(tmpdir, "input.pdf"), png_path)
            return png_path
        except ImportError:
            pass  # pymupdf not installed, fall through

    # Strategy 2: latex + dvipng (fastest, best quality)
    if _has_command("latex") and _has_command("dvipng"):
        result = _run(
            ["latex", "-interaction=nonstopmode", "-halt-on-error", "input.tex"],
            cwd=tmpdir,
        )
        if result.returncode != 0:
            print("LaTeX compilation failed:", file=sys.stderr)
            print(result.stdout, file=sys.stderr)
            sys.exit(1)

        png_file = os.path.join(tmpdir, "input.png")
        result = _run([
            "dvipng", "-D", "600", "-T", "tight",
            "-o", png_file, os.path.join(tmpdir, "input.dvi"),
        ])
        if result.returncode == 0:
            return png_file

    # Strategy 3: pdflatex + pymupdf
    if _has_command("pdflatex"):
        try:
            import fitz  # noqa: F401
            result = _run(
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "input.tex"],
                cwd=tmpdir,
            )
            if result.returncode != 0:
                print("pdflatex compilation failed:", file=sys.stderr)
                print(result.stdout, file=sys.stderr)
                sys.exit(1)
            png_path = os.path.join(tmpdir, "input.png")
            _fitz_pdf_to_png(os.path.join(tmpdir, "input.pdf"), png_path)
            return png_path
        except ImportError:
            pass

    # Strategy 4: pdflatex + ghostscript
    if _has_command("pdflatex") and _has_command("gs"):
        result = _run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "input.tex"],
            cwd=tmpdir,
        )
        if result.returncode != 0:
            print("pdflatex compilation failed:", file=sys.stderr)
            print(result.stdout, file=sys.stderr)
            sys.exit(1)

        pdf_path = os.path.join(tmpdir, "input.pdf")

        bbox_result = _run([
            "gs", "-dSAFER", "-dBATCH", "-dNOPAUSE",
            "-sDEVICE=bbox", pdf_path,
        ])
        bbox_line = None
        for line in bbox_result.stderr.splitlines():
            if line.startswith("%%HiResBoundingBox:"):
                bbox_line = line
                break

        if bbox_line:
            parts = bbox_line.split(":")[1].strip().split()
            x0, y0, x1, y1 = [float(p) for p in parts]
            pad = 4
            png_out = os.path.join(tmpdir, "input.png")
            result = _run([
                "gs", "-dSAFER", "-dBATCH", "-dNOPAUSE",
                "-sDEVICE=png16m", "-r600",
                f"-sOutputFile={png_out}",
                f"-dDEVICEWIDTHPOINTS={x1 - x0 + 2 * pad:.1f}",
                f"-dDEVICEHEIGHTPOINTS={y1 - y0 + 2 * pad:.1f}",
                "-dFIXEDMEDIA",
                "-c",
                f"<< /BeginPage {{ {-(x0 - pad):.1f} {-(y0 - pad):.1f} translate }} >> setpagedevice",
                "-f", pdf_path,
            ])
        else:
            result = _run([
                "gs", "-dSAFER", "-dBATCH", "-dNOPAUSE",
                "-sDEVICE=png16m", "-r600",
                f"-sOutputFile={os.path.join(tmpdir, 'input.png')}",
                pdf_path,
            ])

        png_file = os.path.join(tmpdir, "input.png")
        if result.returncode == 0 and os.path.exists(png_file):
            return png_file
        print("Ghostscript conversion failed:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    # Strategy 5: pdflatex + pdftoppm (poppler)
    if _has_command("pdflatex") and _has_command("pdftoppm"):
        result = _run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "input.tex"],
            cwd=tmpdir,
        )
        if result.returncode != 0:
            print("pdflatex compilation failed:", file=sys.stderr)
            print(result.stdout, file=sys.stderr)
            sys.exit(1)

        prefix = os.path.join(tmpdir, "input")
        result = _run([
            "pdftoppm", "-png", "-r", "600", "-singlefile",
            os.path.join(tmpdir, "input.pdf"), prefix,
        ])
        if result.returncode == 0:
            return prefix + ".png"
        print("pdftoppm conversion failed:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    print(
        "No supported conversion tools found.\n"
        "Install one of:\n"
        "  - pip install latex-to-png[batteries]  (matplotlib, no system tools needed)\n"
        "  - latex + dvipng (usually bundled with TeX Live)\n"
        "  - pdflatex + ghostscript (gs)\n"
        "  - pdflatex + poppler-utils (pdftoppm)",
        file=sys.stderr,
    )
    sys.exit(1)


def render(latex_string, filename, directory):
    """Render a LaTeX string to a PNG file."""
    if not filename.endswith(".png"):
        filename += ".png"

    os.makedirs(directory, exist_ok=True)
    output_path = os.path.join(directory, filename)

    if _needs_math_wrap(latex_string):
        content = f"${latex_string}$"
    else:
        content = latex_string

    # Strategy 0: matplotlib mathtext — pure pip, no system tools needed.
    # Falls through on ImportError or unsupported LaTeX (e.g. \begin{align}).
    tmp_png = tempfile.mktemp(suffix=".png", prefix="latex_to_png_")
    if _render_with_matplotlib(content, tmp_png):
        shutil.move(tmp_png, output_path)
        print(f"Saved to {output_path}")
        return

    # Fall back to LaTeX-based pipeline
    tex_source = TEX_TEMPLATE.format(content=content)
    tmpdir = tempfile.mkdtemp(prefix="latex_to_png_")
    try:
        with open(os.path.join(tmpdir, "input.tex"), "w") as f:
            f.write(tex_source)

        png_file = _compile_and_convert(tmpdir)
        shutil.copy2(png_file, output_path)
        print(f"Saved to {output_path}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description="Convert a LaTeX string to a PNG file."
    )
    parser.add_argument("latex_string", help="LaTeX string to render")
    parser.add_argument("filename", help="Output filename (with or without .png)")
    parser.add_argument(
        "-d",
        "--directory",
        default=os.path.join(os.getcwd(), "latex-to-png"),
        help="Output directory (default: ./latex-to-png/)",
    )

    args = parser.parse_args()
    render(args.latex_string, args.filename, args.directory)


if __name__ == "__main__":
    main()
