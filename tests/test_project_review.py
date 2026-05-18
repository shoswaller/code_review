"""tests/test_project_review.py —— 项目审查模式测试"""
import sys
from pathlib import Path
import tempfile
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from code_review.project_scanner import (
    discover_files,
    count_stats,
    analyze_project_structure,
)
from code_review.project_reporter import (
    create_file_summary,
    compose_project_report,
    render_project_report,
    parse_findings_from_report,
)
from code_review.schemas import (
    FileReviewSummary,
    ProjectOverview,
    ProjectReviewReport,
)


class TestProjectScanner:
    """测试项目扫描器。"""

    def test_discover_files_python(self):
        """发现 Python 文件。"""
        with tempfile.TemporaryDirectory() as tmp:
            # 创建测试文件
            Path(tmp, "main.py").write_text("print('hello')")
            Path(tmp, "utils.py").write_text("def foo(): pass")
            Path(tmp, "test.js").write_text("console.log('hi')")
            Path(tmp, "README.md").write_text("# Hello")
            # 创建被排除的目录
            Path(tmp, "__pycache__").mkdir()
            Path(tmp, "__pycache__", "cached.pyc").write_text("")

            files = discover_files(tmp, include_exts=[".py"])
            assert len(files) == 2
            names = [Path(f).name for f in files]
            assert "main.py" in names
            assert "utils.py" in names

    def test_discover_files_excludes_dirs(self):
        """排除特定目录。"""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "src").mkdir()
            Path(tmp, "src", "app.py").write_text("x=1")
            Path(tmp, "node_modules").mkdir()
            Path(tmp, "node_modules", "lib.js").write_text("var x=1;")
            Path(tmp, ".git").mkdir()
            Path(tmp, ".git", "config").write_text("")

            files = discover_files(tmp, exclude_dirs=["node_modules", ".git"])
            assert len(files) == 1
            assert Path(files[0]).name == "app.py"

    def test_count_stats(self):
        """统计代码行数和符号。"""
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp, "test.py")
            fp.write_text("""
import os

def hello():
    return "world"

class MyClass:
    def method(self):
        pass
""")
            stats = count_stats(str(fp))
            assert stats["lines"] > 0
            assert stats["functions"] == 2  # hello + method
            assert stats["classes"] == 1

    def test_analyze_project_structure(self):
        """分析项目结构。"""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "main.py").write_text("def main(): pass\n")

            ov = analyze_project_structure(tmp, [str(Path(tmp, "main.py"))])
            assert isinstance(ov, ProjectOverview)
            assert ov.total_files == 1
            assert ov.total_lines > 0
            assert ov.language_distribution.get("Python") == 1


class TestProjectReporter:
    """测试项目报告生成器。"""

    def test_parse_findings_from_report(self):
        """从报告文本中提取问题统计。"""
        report = """
        ## 审查发现
        - [Critical] `file.py:L10-L15` (security): SQL injection → Use parameterized queries
        - [Major] `file.py:L25-L30` (style): Bad naming → Rename variable
        - [Minor] `file.py:L40` (logic): Unnecessary condition → Simplify
        """
        findings = parse_findings_from_report(report)
        assert findings["critical_count"] == 1
        assert findings["major_count"] == 1
        assert findings["minor_count"] == 1
        assert findings["nit_count"] == 0

    def test_create_file_summary(self):
        """创建单文件审查摘要。"""
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp, "test.py")
            fp.write_text("def foo(): pass\n")
            report = "[Critical] (security): SQL injection risk"

            summary = create_file_summary(str(fp), "Request Changes", report)
            assert isinstance(summary, FileReviewSummary)
            assert summary.verdict == "Request Changes"
            assert summary.critical_count == 1
            assert summary.security_issues == 1
            assert summary.lines > 0

    def test_compose_and_render_report(self):
        """生成并渲染项目报告。"""
        with tempfile.TemporaryDirectory() as tmp:
            # 创建两个测试文件
            fp1 = Path(tmp, "a.py")
            fp1.write_text("def foo(): pass\n")
            fp2 = Path(tmp, "b.py")
            fp2.write_text("def bar(): pass\n")

            summary1 = create_file_summary(str(fp1), "Approve", "No issues")
            summary2 = create_file_summary(
                str(fp2), "Request Changes",
                "[Critical] (security): SQL injection"
            )

            report = compose_project_report(
                project_root=tmp,
                file_summaries=[summary1, summary2],
                file_reports={str(fp1): "ok", str(fp2): "issues"},
            )
            assert isinstance(report, ProjectReviewReport)
            assert report.overview.total_files == 2
            assert report.total_findings > 0
            assert 0 <= report.health_score <= 100
            assert len(report.top_issues) > 0

            rendered = render_project_report(report)
            assert "项目代码审查报告" in rendered
            assert "健康度评分" in rendered
            assert "a.py" in rendered
            assert "b.py" in rendered

    def test_health_score_perfect(self):
        """完美代码的健康度评分应为 100。"""
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp, "perfect.py")
            fp.write_text("def add(a, b): return a + b\n")
            summary = create_file_summary(str(fp), "Approve", "")
            report = compose_project_report(
                project_root=tmp,
                file_summaries=[summary],
                file_reports={str(fp): ""},
            )
            assert report.health_score == 100
            assert report.recommendation is not None


class TestSchemas:
    """测试新增的数据模型。"""

    def test_file_review_summary(self):
        s = FileReviewSummary(
            file_path="/a/b.py", verdict="Approve",
            lines=100, critical_count=0, major_count=1, minor_count=2, nit_count=0,
            style_issues=1, security_issues=0, performance_issues=0, logic_issues=2,
        )
        assert s.critical_count == 0
        assert s.major_count == 1

    def test_project_overview(self):
        ov = ProjectOverview(
            project_root="/test",
            total_files=5, total_lines=500,
            total_functions=30, total_classes=5,
            language_distribution={"Python": 5},
            directory_tree="test/\n├── main.py",
        )
        assert ov.total_files == 5
        assert ov.language_distribution["Python"] == 5

    def test_project_review_report(self):
        ov = ProjectOverview(
            project_root="/test", total_files=1, total_lines=100,
            total_functions=3, total_classes=0,
            language_distribution={"Python": 1}, directory_tree="",
        )
        report = ProjectReviewReport(
            overview=ov,
            file_summaries=[],
            health_score=90,
            total_findings=5,
            critical_findings=[],
            major_findings=["issue1"],
            top_issues=["problem1"],
            recommendation="fix it",
        )
        assert report.health_score == 90
        assert len(report.major_findings) == 1
