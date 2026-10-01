import html
import os
import re
from string import Template

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template.html")

MATHJAX_BLOCK = r"""<script>
  window.MathJax = {
    tex: {
      inlineMath:  [['$','$'], ['\\(','\\)']],
      displayMath: [['$$','$$'], ['\\[','\\]']]
    },
    chtml: {
      scale: 0.85,             /* shrink math to ~85% of body text */
      matchFontHeight: false,  /* stop measuring Amiri's x-height */
      mtextInheritFont: true   /* \text{...} uses the page font */
    },
    options: {
      enableMenu: false        /* no right-click menu in a print PDF */
    }
  };
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-mml-chtml.js" async></script>"""


READY_SCRIPT = """<script>
(function () {
  "use strict";
  function signal(mathOk) {
    window.__MATHJAX_OK__ = Boolean(mathOk);
    window.__DOCUMENT_READY__ = true;
  }
  function tryFinish() {
    if (window.MathJax && window.MathJax.startup && window.MathJax.startup.promise) {
      window.MathJax.startup.promise.then(function () { signal(true); })
                                .catch(function () { signal(false); });
      return true;
    }
    return false;
  }
  window.addEventListener("load", function () {
    if (tryFinish()) { return; }
    var waitedMs = 0;
    var poll = setInterval(function () {
      waitedMs += 250;
      if (tryFinish()) { clearInterval(poll); return; }
      if (waitedMs >= 15000) { clearInterval(poll); signal(false); }
    }, 250);
  });
})();
</script>"""

# توزيع حقول الترويسة على المناطق الثلاث
# توزيع حقول الترويسة على المناطق الثلاث
SIDE_START_FIELDS = [      # العمود الأيمن
    ("الصف", "class_level"),
    ("المادة", "subject_name"),
]
SIDE_END_FIELDS = [        # العمود الأيسر (بعد اسم الأستاذ)
    ("العلامة", "marks"),
    ("المدة", "time"),
]

# ------------------------------------------------------- LaTeX normalizer ----
# Policy: everything renders INLINE. Block/display constructs are rewritten.

_DOLLAR_BLOCK = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_BRACKET_BLOCK = re.compile(r"\\\[([\s\S]+?)\\\]")
_LABEL = re.compile(r"\\label\{[^{}]*\}")

_ENV_ALIASES = {
    "align": "aligned", "align*": "aligned",
    "gather": "gathered", "gather*": "gathered",
    "eqnarray": "aligned", "eqnarray*": "aligned",
    "multline": "aligned", "multline*": "aligned",
}
_ENV_NAMES = "|".join([*_ENV_ALIASES, "equation", "equation*", "displaymath"])
_ENV_BLOCK = re.compile(r"\\begin\{(" + _ENV_NAMES + r")\}([\s\S]*?)\\end\{\1\}")


def _flatten(body: str) -> str:
    """Inline math can't contain hard line breaks — collapse all whitespace."""
    return " ".join(body.split())


def _env_repl(match: re.Match) -> str:
    name, body = match.group(1), match.group(2)
    body = _flatten(_LABEL.sub("", body))
    if name in _ENV_ALIASES:
        alias = _ENV_ALIASES[name]
        return f"$\\begin{{{alias}}}{body}\\end{{{alias}}}$"
    return f"${body}$"


def normalize_latex(text: str) -> str:
    """$$x$$ -> $x$      \\[x\\] -> \\(x\\)
       \\begin{align}..      -> $\\begin{aligned}..\\end{aligned}$        \\begin{equation}..   -> $..$   (\\label{...} stripped)"""
    text = _DOLLAR_BLOCK.sub(lambda m: "$" + _flatten(m.group(1)) + "$", text)
    text = _BRACKET_BLOCK.sub(lambda m: "\\(" + _flatten(m.group(1)) + "\\)", text)
    text = _ENV_BLOCK.sub(_env_repl, text)
    return text

# ----------------------------------------------------------------- HTML ----

def parse_question_file(path: str) -> list[tuple[str, str]]:
    questions = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                question, answer = line.split("|", 1)
                questions.append((question.strip(), answer.strip()))
            else:
                questions.append((line, ""))
    return questions


def _field(label: str, value) -> str:
    return (f'        <div class="field"><span class="field-label">{label}:</span> '
            f'<span class="field-value">{html.escape(str(value))}</span></div>')


def build_side_start(exam: dict) -> str:
    """العمود الأيمن: المستوى ثم المادة."""
    return "\n".join(
        _field(label, exam[key])
        for label, key in SIDE_START_FIELDS
        if exam.get(key) not in (None, "")
    )


def build_side_end(exam: dict) -> str:
    """العمود الأيسر: اسم الأستاذ (بلا تسمية) ثم النقاط ثم المدة."""
    parts = []
    teacher = exam.get("teacher_name")
    if teacher not in (None, ""):
        parts.append(
            f'        <div class="field teacher">'
            f'<span class="field-value">{html.escape(str(teacher))}</span></div>'
        )
    parts.extend(
        _field(label, exam[key])
        for label, key in SIDE_END_FIELDS
        if exam.get(key) not in (None, "")
    )
    return "\n".join(parts)


def build_questions_html(questions: list[dict]) -> str:
    items = []
    for q in questions:
        img = ""
        if q.get("image_path"):
            img = f'\n        <img class="question-image" src="{q["image_path"]}"/>'
        text = normalize_latex(q["text"] or "")
        items.append(
            f'      <li class="question">\n'
            f'        <div class="question-text">{text}</div>{img}\n'
            f'      </li>'
        )
    return "\n".join(items)


def render_exam_html(exam: dict, questions: list[dict]) -> str:
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = Template(f.read())

    name = html.escape(str(exam.get("name") or "Exam"))

    return template.substitute(
        html_title=name,
        exam_name=name,
        exam_year=html.escape(str(exam.get("year") or "")),
        side_start=build_side_start(exam),
        side_end=build_side_end(exam),
        questions_html=build_questions_html(questions),
        mathjax_block=MATHJAX_BLOCK,
        ready_script=READY_SCRIPT,
    )