#!/usr/bin/env python3
"""
Robot Paper Campaign — Daily Automation
========================================
09:00 daily: search arXiv for papers from top ML/Robotics venues,
find first/second authors' GitHub profile → extract email,
send headhunting emails, file daily summary.

Usage:
    python main.py [--max-papers N] [--date-from YYYY-MM-DD] [--dry-run]

Created & maintained by Glen Wei (韦其像)
Email: glen.keeming@gmail.com
Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"""

AUTHOR_EPILOG = (
    "Author: Glen Wei (韦其像) | Email: glen.keeming@gmail.com | "
    "Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"
)

import os, sys, re, json, time, sqlite3, urllib.parse, smtplib
from datetime import datetime, timedelta, date
from xml.etree import ElementTree as ET
from email.mime.text import MIMEText
from email.header import Header

import requests

# ═══════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(WORK_DIR, 'paper_tracker.db')
SUMMARY_DIR = os.path.join(WORK_DIR, 'summaries')
GMAIL_CONFIG_PATH = os.path.expanduser('~/.workbuddy/gmail_config.json')
GITHUB_CONFIG_PATH = os.path.expanduser('~/.workbuddy/github_config.json')

# Venue keywords → papers mention these in title/abstract/comments
VENUE_KEYWORDS = [
    "NeurIPS 2026", "ICML 2026", "ICLR 2026",
    "CVPR 2026", "ECCV 2026",
    "IEEE Trans. Robot", "Int. J. Robot",
    "NeurIPS 2025", "ICML 2025", "ICLR 2025",
    "CVPR 2025", "ICCV 2025",
    "TRO", "IJRR",
]

# arXiv categories to search — only the most relevant
ARXIV_CATEGORIES = [
    "cs.RO",    # Robotics
    "cs.CV",    # Computer Vision
    "cs.LG",    # Machine Learning
    "cs.AI",    # Artificial Intelligence
]

MAX_PAPERS_PER_RUN = 30

# Keywords for relevance filtering — paper must match to be eligible
ROBOTICS_RELEVANCE_KEYWORDS = [
    # Core robotics terms
    "robot", "robotic", "robotics", "humanoid", "bipedal", "legged robot",
    "manipulation", "grasp", "grasping", "prehension", "dexterous",
    "locomotion", "walking", "navigation", "slam", "mapping",
    "motion planning", "path planning", "trajectory optimization",
    "control", "mpc", "model predictive control",
    # Learning & AI for robotics
    "reinforcement learning", "imitation learning", "robot learning",
    "policy learning", "behavior cloning", "inverse reinforcement",
    "rl", "offline rl",
    # Embodied AI
    "embodied", "world model", "foundation model", "vla",
    "vision-language-action", "embodied agent", "embodied ai",
    "sim-to-real", "sim2real", "domain randomization",
    # Perception for robotics
    "point cloud", "3d reconstruction", "depth estimation",
    "pose estimation", "visual navigation", "scene understanding",
    "sensor fusion", "robot perception",
    # Agent & planning
    "agent", "task planning", "tool use", "code generation",
    # Applications
    "autonomous driving", "self-driving", "uav", "drone",
    "autonomous vehicle", "unmanned aerial",
    # Specific robot hardware
    "soft robot", "surgical robot", "medical robot",
    "swarm", "multi-agent", "multi-robot",
]

# Negative keywords — paper with these (and no positive match) is not robotics
ROBOTICS_NEGATIVE_KEYWORDS = [
    "gravitational lens", "cosmolog", "galaxy", "stellar", "astrophys",
    "protein folding", "drug discovery", "molecular dynamics",
    "quantum", "nuclear", "plasma", "fluid dynamics",
    "climate", "weather", "earthquake",
    "nlp", "natural language process", "machine translation",
    "speech recognition", "text generation",
    "recommender", "recommendation system",
    "time series forecasting", "anomaly detection",
    "tabular data", "graph neural network", "gnn",
    "privacy", "federated learning", "differential privacy",
    "adversarial attack", "adversarial robustness",
    "knowledge graph", "information retrieval",
    "computational biology", "bioinformatic",
    "financial", "stock", "trading",
    "theorem proving", "formal verification",
]

RELEVANCE_MIN_MATCHES = 2
"""Minimum number of robotics keywords that must match in title+abstract."""

# Direction classification → JD mapping
DIRECTION_MAP = [
    {
        "name": "具身智能/世界模型",
        "keywords": ["embodied", "world model", "foundation model", "VLA",
                     "vision-language-action", "embodied agent", "embodied ai"],
        "jd_title": "具身智能/世界模型 专家/研究员",
        "jd_duties": "研发下一代具身智能体，构建可泛化的世界模型/基础模型，实现机器人在真实环境中的自主决策与操作",
        "jd_req": "熟悉VLA/世界模型/模仿学习，有机器人真机经验者优先",
        "jd_company": "头部AI与机器人企业",
        "jd_team": "具身智能核心研发",
    },
    {
        "name": "机器人灵巧操作",
        "keywords": ["dexterous", "grasp", "manipulation", "prehension",
                     "pick and place", "robotic hand", "in-hand"],
        "jd_title": "机器人灵巧操作 专家/研究员",
        "jd_duties": "研发高泛化性的机器人操作策略，覆盖灵巧手抓取、双臂协同、柔性物体操作等场景",
        "jd_req": "精通机器人操作、抓取规划或灵巧操控，有真机部署经验者优先",
        "jd_company": "头部AI与机器人企业",
        "jd_team": "机器人操作核心研发",
    },
    {
        "name": "人形机器人/全身控制",
        "keywords": ["humanoid", "bipedal", "whole-body", "full-body",
                     "walking", "locomotion", "legged robot", "humanoid robot"],
        "jd_title": "人形机器人/全身控制 专家/研究员",
        "jd_duties": "研发人形机器人的全身运动控制与行走算法，实现稳定、敏捷的双足运动能力",
        "jd_req": "熟悉人形机器人运动学/动力学、MPC/WBC控制，有真机调试经验",
        "jd_company": "头部人形机器人企业",
        "jd_team": "运动控制核心团队",
    },
    {
        "name": "机器人学习/模仿学习",
        "keywords": ["imitation learning", "reinforcement learning",
                     "robot learning", "policy learning", "behavior cloning",
                     "offline rl", "inverse reinforcement"],
        "jd_title": "机器人学习 专家/研究员",
        "jd_duties": "研发机器人学习算法，利用模仿学习/强化学习实现机器人技能的自主获取与泛化",
        "jd_req": "精通机器人学习、模仿学习或强化学习，有大规模策略训练经验",
        "jd_company": "头部AI与机器人企业",
        "jd_team": "机器人学习核心研发",
    },
    {
        "name": "机器人感知/计算机视觉",
        "keywords": ["point cloud", "3d vision", "3d reconstruction",
                     "pose estimation", "scene understanding", "visual perception",
                     "robot perception", "nerf", "sensor fusion"],
        "jd_title": "机器人感知/计算机视觉 专家/研究员",
        "jd_duties": "研发机器人视觉感知系统，涵盖场景理解、3D重建、物体检测与位姿估计等方向",
        "jd_req": "精通计算机视觉或机器人感知，有顶会论文发表经验",
        "jd_company": "头部AI与机器人企业",
        "jd_team": "感知核心团队",
    },
    {
        "name": "导航/SLAM",
        "keywords": ["navigation", "slam", "mapping", "localization",
                     "path planning", "exploration", "visual navigation", "vln"],
        "jd_title": "机器人导航/SLAM 专家/研究员",
        "jd_duties": "研发自主导航与SLAM系统，实现机器人在复杂环境中的精准定位与自主移动",
        "jd_req": "精通SLAM、导航规划或视觉导航，有真机经验者优先",
        "jd_company": "头部机器人企业",
        "jd_team": "导航核心团队",
    },
    {
        "name": "AI Agent/大模型",
        "keywords": ["agent", "llm", "large language model", "reasoning",
                     "task planning", "vlm", "vision language model", "multi-modal",
                     "code generation", "tool use"],
        "jd_title": "AI Agent/大模型 专家/研究员",
        "jd_duties": "研发基于大模型/多模态模型的智能Agent系统，实现复杂任务的理解、规划与执行",
        "jd_req": "精通LLM/VLM、AI Agent或推理规划，有相关论文或开源项目经验",
        "jd_company": "头部AI企业",
        "jd_team": "AI Agent核心研发",
    },
    {
        "name": "控制/运动规划",
        "keywords": ["control", "motion planning", "trajectory",
                     "mpc", "model predictive control", "optimal control",
                     "trajectory optimization"],
        "jd_title": "机器人控制/运动规划 专家/研究员",
        "jd_duties": "研发先进控制与运动规划算法，提升机器人在复杂动态环境中的运动能力",
        "jd_req": "精通最优控制、MPC或轨迹优化，有真机部署经验",
        "jd_company": "头部机器人企业",
        "jd_team": "控制核心团队",
    },
]

# ═══════════════════════════════════════════
# Database
# ═══════════════════════════════════════════

class PaperTracker:
    def __init__(self, db_path):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_papers (
                arxiv_id TEXT PRIMARY KEY,
                title TEXT, venue TEXT,
                first_author TEXT, second_author TEXT,
                direction TEXT, emails_sent TEXT,
                highlight TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS run_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT, papers_found INTEGER,
                papers_processed INTEGER, emails_sent INTEGER,
                uncertain_count INTEGER, summary_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.close()

    def is_processed(self, arxiv_id):
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT 1 FROM processed_papers WHERE arxiv_id=?", (arxiv_id,))
        r = cur.fetchone()
        conn.close()
        return r is not None

    def mark_processed(self, arxiv_id, title, venue, first_author, second_author,
                       direction, emails_sent, highlight):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR IGNORE INTO processed_papers
            (arxiv_id, title, venue, first_author, second_author, direction, emails_sent, highlight)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (arxiv_id, title, venue, first_author, second_author,
              direction, json.dumps(emails_sent), highlight))
        conn.commit()
        conn.close()

    def log_run(self, run_date, found, processed, sent, uncertain, summary_path):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""INSERT INTO run_log VALUES (NULL,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
                     (run_date, found, processed, sent, uncertain, summary_path))
        conn.commit()
        conn.close()


# ═══════════════════════════════════════════
# arXiv scraper (optimized)
# ═══════════════════════════════════════════

class ArxivScraper:
    API_URL = "https://export.arxiv.org/api/query"

    def __init__(self):
        import urllib.request, ssl
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    @staticmethod
    def _urlopen(url, timeout=90):
        """Fetch URL via urllib, bypassing system proxy."""
        import ssl, urllib.request as ureq
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = ureq.Request(url, headers={
            'User-Agent': 'RobotPaperCampaign/1.0'
        })
        # Explicitly disable proxy for this request
        proxy_handler = ureq.ProxyHandler({})
        opener = ureq.build_opener(proxy_handler)
        return opener.open(req, timeout=timeout).read().decode('utf-8')

    def search(self, keywords, categories, date_from, date_to, max_results=300):
        """
        Search arXiv — one query per category using simple cat queries.
        Filter results by date range locally.
        """
        import urllib.parse
        all_entries = []
        seen_ids = set()

        for cat in categories:
            # Simple category-only query — arXiv API handles this much better
            url = (f"{self.API_URL}?search_query=cat:{cat}"
                   f"&start=0&max_results={min(max_results * 2, 500)}"
                   f"&sortBy=submittedDate&sortOrder=descending")

            try:
                text = self._urlopen(url, timeout=90)
                entries = self._parse_response(text, date_from, date_to)
                for e in entries:
                    if e['id'] not in seen_ids:
                        seen_ids.add(e['id'])
                        all_entries.append(e)
                print(f"   [{cat}] found {len(entries)} papers (in date range)")
            except Exception as ex:
                print(f"   [WARN] arXiv query failed for {cat}: {ex}")

            # Wait generously between requests — arXiv rate limits aggressively
            import time as _time
            _time.sleep(10)

        all_entries.sort(key=lambda x: x['published'], reverse=True)
        return all_entries

    def _parse_response(self, xml_text, date_from, date_to):
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
        entries = []
        root = ET.fromstring(xml_text)

        for entry in root.findall('atom:entry', ns):
            try:
                id_el = entry.find('atom:id', ns)
                full_id = id_el.text.strip() if id_el is not None else ''
                paper_id = full_id.split('/')[-1].split('v')[0]

                pub_el = entry.find('atom:published', ns)
                published = pub_el.text.strip()[:10] if pub_el is not None else ''
                if published < date_from or published > date_to:
                    continue

                title_el = entry.find('atom:title', ns)
                title = title_el.text.strip().replace('\n', ' ').replace('  ', ' ') if title_el is not None else ''

                abs_el = entry.find('atom:summary', ns)
                abstract = abs_el.text.strip().replace('\n', ' ').replace('  ', ' ') if abs_el is not None else ''

                authors = []
                for au in entry.findall('atom:author', ns):
                    name_el = au.find('atom:name', ns)
                    if name_el is not None and name_el.text:
                        authors.append(name_el.text.strip())

                comment_el = entry.find('arxiv:comment', ns)
                comment = comment_el.text.strip() if comment_el is not None else ''

                categories = [cat.get('term', '') for cat in entry.findall('atom:category', ns)]
                venue = self._detect_venue(title, abstract, comment, categories)

                entries.append({
                    'id': paper_id, 'title': title, 'abstract': abstract,
                    'authors': authors, 'comment': comment,
                    'categories': categories, 'published': published,
                    'venue': venue,
                    'url': f'https://arxiv.org/abs/{paper_id}',
                })
            except:
                continue
        return entries

    def _detect_venue(self, title, abstract, comment, categories):
        text = f"{title} {abstract} {comment}".lower()
        for kw in ["neurips", "icml", "iclr", "cvpr", "iccv", "eccv"]:
            if kw in text:
                return kw.upper()
        if "ieee transactions on robotics" in text or "ieee trans. robot" in text:
            return "TRO"
        if "international journal of robotics research" in text or "int. j. robot" in text:
            return "IJRR"
        if "robotics and autonomous systems" in text:
            return "RAS"
        return "unknown"


# ═══════════════════════════════════════════
# Relevance filter
# ═══════════════════════════════════════════

def is_robotics_relevant(paper):
    """Check if a paper is truly robotics/embodied AI related."""
    text = f"{paper['title']} {paper['abstract']}".lower()

    # Count positive keyword matches
    pos_matches = sum(1 for kw in ROBOTICS_RELEVANCE_KEYWORDS if kw.lower() in text)

    # Count negative keyword matches
    neg_matches = sum(1 for kw in ROBOTICS_NEGATIVE_KEYWORDS if kw.lower() in text)

    # Papers in cs.RO get an auto boost
    cat_bonus = 2 if 'cs.RO' in paper['categories'] else 0

    # Papers in cs.CV with 1+ positive match are usually robotics-connected
    cv_bonus = 1 if 'cs.CV' in paper['categories'] and pos_matches >= 1 else 0

    score = pos_matches + cat_bonus + cv_bonus - neg_matches

    # Decision
    if cat_bonus >= 2 and pos_matches >= 1:
        return True  # cs.RO with at least some robotics keywords
    if pos_matches >= RELEVANCE_MIN_MATCHES and neg_matches < 1:
        return True  # Strong positive signal, no negative
    if pos_matches >= 1 and neg_matches == 0 and ('cs.RO' in paper['categories'] or 'cs.CV' in paper['categories']):
        return True  # Marginal but in a robotics-adjacent category
    if pos_matches >= 3:
        return True  # Very strong positive signal overrides everything

    return False


# ═══════════════════════════════════════════
# Chinese name detection
# ═══════════════════════════════════════════

# Common Chinese surnames (pinyin) — covers ~95%+ of Chinese names
CHINESE_SURNAMES_PINYIN = {
    'wang','li','zhang','liu','chen','yang','zhao','huang','zhou','wu',
    'xu','sun','hu','zhu','gao','lin','he','guo','ma','luo',
    'liang','song','zheng','xie','han','tang','feng','yu','dong','xiao',
    'cheng','cao','yuan','deng','xu','fu','shen','zeng','peng','lv',
    'su','lu','jiang','cai','jia','ding','wei','xue','ye','yan',
    'yu','pan','du','dai','xia','zhong','wang','tian','ren','jiang',
    'fan','fang','shi','yao','tan','liao','zou','xiong','jin','lu',
    'hao','kong','bai','cui','kang','mao','qiu','qin','jiang','shi',
    'gu','hou','shao','meng','long','wan','duan','qian','tang','yin',
    'li','yi','chang','wu','qiao','he','lai','gong','wen',
    'ouyang','taishi','duanmu','shangguan','sima','dongfang','dugu','nangong',
    'nie','xing','tong','kong','shen','di','bao','wu','ji','yu',
    'shui','dou','yu','yang','feng','hua','mi','wei','tong','sang',
    'kai','zhan','zhuo','chu','che','lai','lan','guan','chai','she',
    'xiang','qiang','kuang','bao','rong','shan','tong','nong',
}

def is_chinese_name(name):
    """Detect if an author name is Chinese.
    
    Handles formats:
    1. Chinese characters: 黄守旺, 张伟
    2. Pinyin + surname: Shouwang Huang, Wenhao Li
    3. Surname + given: Wang Xiaoming
    """
    name = name.strip()
    if not name:
        return False
    
    # Format 1: Full Chinese characters (2-4 chars)
    if re.fullmatch(r'[\u4e00-\u9fff]{2,4}', name):
        return True
    
    # Format 2 & 3: Pinyin name "Given Surname" or "Surname Given"
    parts = name.split()
    if len(parts) == 2:
        first, last = parts[0].lower(), parts[1].lower()
        if last in CHINESE_SURNAMES_PINYIN:     # "Shouwang Huang"
            return True
        if first in CHINESE_SURNAMES_PINYIN:    # "Wang Xiaoming"
            return True
    
    # 3+ parts → not Chinese (e.g. "Tharun Kumar Tiruppali")
    return False


# ═══════════════════════════════════════════
# Email extraction — GitHub profile as primary source
# ═══════════════════════════════════════════

class EmailFinder:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        })
        # Load GitHub API token if available
        self.github_token = None
        if os.path.exists(GITHUB_CONFIG_PATH):
            try:
                with open(GITHUB_CONFIG_PATH) as f:
                    cfg = json.load(f)
                    self.github_token = cfg.get('token', '').strip()
                if self.github_token:
                    print(f"   [CONFIG] GitHub token loaded ({self.github_token[:8]}...)")
            except:
                pass

    def _github_api_session(self):
        """Return headers dict with optional GitHub token."""
        hdrs = {'Accept': 'application/vnd.github.v3+json'}
        if self.github_token:
            hdrs['Authorization'] = f'token {self.github_token}'
        return hdrs

    def find_email(self, author_name, paper_title, paper_data=None):
        """Try multiple strategies to find an author's email, in order.
        
        Reordered for efficiency: arXiv metadata first (instant if present),
        then GitHub API (fast with token), then web-based fallbacks.
        """
        email = None

        # Strategy 1 (FAST): Extract email from arXiv paper data (abstract + comment)
        # This is instant — the data is already in memory
        if paper_data:
            email = self._extract_from_arxiv_data(paper_data)
            if email:
                print(f"   📧 {author_name}: found in arXiv metadata")
                return email

        # Strategy 2 (FAST with token): GitHub API search by full name
        email = self._github_api_search(author_name)
        if email:
            print(f"   📧 {author_name}: found via GitHub API")
            return email

        # Strategy 3 (SLOW): GitHub web search + profile scrape
        email = self._github_web_scrape(author_name)
        if email:
            print(f"   📧 {author_name}: found via GitHub web")
            return email

        # Strategy 4 (SLOW): Google Scholar profile scrape
        email = self._google_scholar_scrape(author_name)
        if email:
            print(f"   📧 {author_name}: found via Google Scholar")
            return email

        # Strategy 5 (SLOWEST): Web search for personal page
        email = self._web_search_email(author_name, paper_title)
        if email:
            print(f"   📧 {author_name}: found via web search")
            return email

        print(f"   ❓ {author_name}: email not found")
        return None

    # ── Strategy 1: GitHub API ──────────────────────────

    def _github_api_search(self, author_name):
        """GitHub API: search users by full name, get profile email."""
        # Handle Chinese names — try surname first
        search_names = [author_name]
        if re.match(r'^[\u4e00-\u9fff]{2,4}$', author_name):
            search_names.append(author_name[:1])  # Just surname

        for name in search_names:
            q = urllib.parse.quote(f'{name} in:fullname')
            url = f'https://api.github.com/search/users?q={q}&per_page=3'
            try:
                resp = self.session.get(url, timeout=10,
                    headers=self._github_api_session(),
                    verify=False)
                if resp.status_code == 403 and self.github_token:
                    print(f"   [WARN] GitHub API 403 (token may be invalid or expired)")
                    break
                if resp.status_code == 403:
                    print(f"   [WARN] GitHub API rate limited (no token)")
                    break
                if resp.status_code != 200:
                    continue
                for user in resp.json().get('items', []):
                    purl = f"https://api.github.com/users/{user['login']}"
                    presp = self.session.get(purl, timeout=10,
                        headers=self._github_api_session(),
                        verify=False)
                    if presp.status_code == 200:
                        email = presp.json().get('email')
                        if email:
                            return email
                    time.sleep(0.3)
            except:
                continue
            time.sleep(1)
        return None

    # ── Strategy 2: GitHub web scrape ───────────────────

    def _github_web_scrape(self, author_name):
        """GitHub web search → scrape profile page for email."""
        try:
            q = urllib.parse.quote(author_name)
            # Search GitHub users
            url = f'https://github.com/search?q={q}&type=users'
            resp = self.session.get(url, timeout=15, verify=False)
            if resp.status_code != 200:
                return None

            # Find user profile URLs
            profile_urls = re.findall(r'href="(/([\w.-]+))"', resp.text)
            seen = set()
            for path, username in profile_urls:
                if username in seen or not username:
                    continue
                seen.add(username)
                if len(seen) > 5:
                    break

                # Fetch profile page
                purl = f'https://github.com{path}'
                presp = self.session.get(purl, timeout=15, verify=False)
                if presp.status_code != 200:
                    continue

                html = presp.text
                # GitHub shows email as: href="mailto:email@example.com"
                emails = re.findall(r'href="mailto:([^"]+)"', html)
                if emails:
                    return emails[0]
                time.sleep(0.5)
        except:
            pass
        return None

    # ── Strategy 3: arXiv metadata extraction ──────────

    def _extract_from_arxiv_data(self, paper_data):
        """Extract email from arXiv paper metadata we already have.
        
        Many arXiv papers embed the corresponding author's email
        directly in the abstract text or comment field."""
        texts_to_check = []
        if paper_data.get('abstract'):
            texts_to_check.append(paper_data['abstract'])
        if paper_data.get('comment'):
            texts_to_check.append(paper_data['comment'])
        if paper_data.get('url'):
            texts_to_check.append(paper_data['url'])

        for text in texts_to_check:
            emails = re.findall(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', text)
            for e in emails:
                e_clean = e.strip().lstrip('.,;:()[]{}<> "\'').rstrip('.,;:()[]{}<> "\'/?')
                if self._is_valid_academic_email(e_clean):
                    return e_clean
        return None

    # ── Strategy 4: Google Scholar ─────────────────────

    def _google_scholar_scrape(self, author_name):
        """Search Google Scholar profiles, scrape for email."""
        queries = [
            f'{author_name} "Google Scholar" email',
            f'{author_name} scholar.google.com',
        ]
        for q in queries:
            try:
                encoded = urllib.parse.quote(q)
                url = f'https://html.duckduckgo.com/html/?q={encoded}'
                resp = self.session.get(url, timeout=15,
                    headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
                if resp.status_code != 200:
                    continue

                html = resp.text

                # Look for Google Scholar profile links
                scholar_urls = re.findall(
                    r'https?://scholar\.google\.com(?:\.\w+)?/citations\?user=[\w-]+',
                    html
                )
                for surl in scholar_urls[:3]:
                    try:
                        presp = self.session.get(surl, timeout=15, verify=False)
                        if presp.status_code == 200:
                            # Google Scholar profiles often have email in format: email@domain
                            emails = re.findall(
                                r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+',
                                presp.text
                            )
                            for e in emails:
                                e_clean = e.strip().lstrip('.,;:()[]{}<> "\'').rstrip('.,;:()[]{}<> "\'/?')
                                if self._is_valid_academic_email(e_clean):
                                    return e_clean
                    except:
                        continue
                    time.sleep(1.5)

                # Fallback: extract email from the search results page directly
                emails = self._extract_emails(html)
                if emails:
                    return emails[0]
            except:
                continue
            time.sleep(2)
        return None

    # ── Strategy 5: Web search fallback ─────────────────

    def _web_search_email(self, author_name, paper_title):
        """Search the web for author's email (personal page, lab page, etc.)."""
        # Extract meaningful paper keywords (first ~6 words, skip short words)
        title_words = [w for w in paper_title.split() if len(w) > 3][:6]
        title_kw = ' '.join(title_words)

        queries = [
            f'{author_name} email',
            f'{author_name} {title_kw}',
            f'{author_name} university email',
            f'{author_name} "personal page"',
            f'{author_name} lab page contact',
        ]
        for q in queries:
            try:
                encoded = urllib.parse.quote(q)
                # Try DuckDuckGo (more permissive than Google)
                url = f'https://html.duckduckgo.com/html/?q={encoded}'
                resp = self.session.get(url, timeout=15,
                    headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
                if resp.status_code == 200:
                    emails = self._extract_emails(resp.text)
                    if emails:
                        return emails[0]
            except:
                continue
            time.sleep(2)
        return None

    def _extract_emails(self, text):
        """Extract emails from HTML, filtering aggressively."""
        emails = re.findall(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', text)
        valid = []
        junk_domains = ['arxiv.org', 'example.com', 'w3.org', 'schema.org',
                       'github.com', 'google.com', 'youtube.com', 'facebook.com',
                       'twitter.com', 'linkedin.com', 'scholar.google',
                       'orcid.org', 'ieee.org', 'acm.org', 'doi.org',
                       'crossref.org', 'creativecommons', 'whatsapp.com',
                       'weixin.qq.com', 'statcounter.com', 'apache.org',
                       'python.org', 'javascript.com', 'jquery.com',
                       'github.io', 'gitlab.com', 'bitbucket.org',
                       'sourceforge.net', 'slideshare.net', 'medium.com']
        for e in emails:
            e = e.strip().lstrip('.,;:()[]{}<> "\'').rstrip('.,;:()[]{}<> "\'/?')
            if '@' not in e or e.count('@') != 1 or len(e) < 8:
                continue
            local, domain = e.split('@')
            domain = domain.lower()
            # Reject junk domains
            if any(j in domain for j in junk_domains):
                continue
            # Local part must be at least 3 chars (prevents "g@gmail.com")
            if len(local) < 3:
                continue
            # Local part should look like a name, not random digits
            if local.isdigit():
                continue
            # Must have a dot in the domain (e.g. .com, .edu, .cn)
            if '.' not in domain:
                continue
            valid.append(e)
        return list(set(valid))

    def _is_valid_academic_email(self, email):
        """Strict check for academic/personal email (not junk/generic)."""
        junk_domains = ['arxiv.org', 'example.com', 'w3.org', 'schema.org',
                       'github.com', 'google.com', 'youtube.com', 'facebook.com',
                       'twitter.com', 'linkedin.com', 'scholar.google',
                       'orcid.org', 'ieee.org', 'acm.org', 'doi.org',
                       'crossref.org', 'creativecommons', 'whatsapp.com',
                       'weixin.qq.com', 'statcounter.com', 'apache.org',
                       'python.org', 'javascript.com', 'jquery.com',
                       'github.io', 'gitlab.com', 'bitbucket.org',
                       'sourceforge.net', 'slideshare.net', 'medium.com',
                       'noreply', 'no-reply', 'donotreply']
        try:
            e = email.strip().lstrip('.,;:()[]{}<> "\'').rstrip('.,;:()[]{}<> "\'/?')
            if '@' not in e or e.count('@') != 1 or len(e) < 8:
                return False
            local, domain = e.split('@')
            domain = domain.lower()
            if any(j in domain for j in junk_domains):
                return False
            if len(local) < 3 or local.isdigit():
                return False
            if '.' not in domain:
                return False
            return True
        except:
            return False


# ═══════════════════════════════════════════
# JD Generator
# ═══════════════════════════════════════════

class JDGenerator:
    def classify(self, title, abstract):
        text = f"{title} {abstract}".lower()
        for direction in DIRECTION_MAP:
            for kw in direction["keywords"]:
                if kw.lower() in text:
                    return direction
        return DIRECTION_MAP[0]  # Default

    def generate(self, direction, paper):
        abstract_lower = paper['abstract'].lower()
        tech_tags = []
        tech_map = {
            "diffusion": "扩散模型", "transformer": "Transformer",
            "reinforcement learning": "强化学习", "imitation learning": "模仿学习",
            "vla": "VLA模型", "world model": "世界模型",
            "mpc": "模型预测控制", "nerf": "NeRF",
            "gaussian splatting": "3D高斯泼溅", "llm": "大语言模型",
            "vlm": "视觉语言模型", "slam": "SLAM",
            "rl": "强化学习", "nn": "神经网络",
        }
        for eng, cn in tech_map.items():
            if eng in abstract_lower:
                tech_tags.append(cn)

        return {
            'jd_title': direction['jd_title'],
            'jd_duties': direction['jd_duties'],
            'jd_req': direction['jd_req'],
            'jd_company': direction['jd_company'],
            'jd_team': direction['jd_team'],
            'tech_tags': "、".join(tech_tags[:3]) if tech_tags else direction['name'],
            'direction_name': direction['name'],
            'paper_title': paper['title'][:120],
        }


# ═══════════════════════════════════════════
# Email Sender
# ═══════════════════════════════════════════

import socket, ssl

# ═══════════════════════════════════════════
# Proxy-aware socket (bypasses system proxy blocking)
# ═══════════════════════════════════════════

PROXY_HOST = '127.0.0.1'
PROXY_PORT = 7890

def _proxy_create_connection(addr, timeout=None, source_address=None, **kwargs):
    """Override socket.create_connection to tunnel through HTTP CONNECT proxy."""
    host, port = addr
    # Only proxy SMTP connections to Gmail
    if host in ('smtp.gmail.com',):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout or 30)
        sock.connect((PROXY_HOST, PROXY_PORT))
        req = f'CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n'
        sock.sendall(req.encode())
        resp = sock.recv(4096)
        if b'200' not in resp:
            sock.close()
            raise ConnectionError(f'Proxy CONNECT failed to {host}:{port}')
        return sock
    # Use original socket.create_connection for everything else
    return _orig_create_connection(addr, timeout, source_address)

# Monkey-patch socket.create_connection BEFORE smtplib uses it
import socket as _socket
_orig_create_connection = _socket.create_connection
_socket.create_connection = _proxy_create_connection


# ═══════════════════════════════════════════
# Email Sender
# ═══════════════════════════════════════════

class EmailSender:
    def __init__(self):
        with open(GMAIL_CONFIG_PATH) as f:
            self.config = json.load(f)
        # System proxy for CONNECT tunneling
        self.proxy_host = '127.0.0.1'
        self.proxy_port = 7897

    def _proxy_connect(self, target_host, target_port):
        """Create a TCP connection through the HTTP CONNECT proxy tunnel."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect((self.proxy_host, self.proxy_port))
        # Send CONNECT request
        req = f'CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n\r\n'
        sock.sendall(req.encode())
        resp = sock.recv(4096)
        if b'200' not in resp:
            sock.close()
            raise ConnectionError(f'Proxy CONNECT failed: {resp[:200]}')
        return sock

    def send(self, to_addr, author_name, jd_info):
        # Greeting logic
        if re.match(r'^[A-Z][a-zéèêë]+ [A-Z][a-zéèêë]+$', author_name):
            greeting = author_name.split()[0]
        elif re.match(r'^[\u4e00-\u9fff]{2,4}$', author_name):
            greeting = f"{author_name}"
        else:
            greeting = author_name.split()[0] if ' ' in author_name else author_name

        subject = f"{jd_info['direction_name']}方向职位机会｜交个朋友"

        # Recruiter identity comes from gmail_config.json (optional fields);
        # falls back to neutral placeholders when not configured.
        recruiter = self.config.get('recruiter_name', 'AI人才顾问')
        wechat = self.config.get('wechat', '（可加微信详聊，见签名）')
        signature = self.config.get('signature', '[您的姓名]\n[公司/职位]\n[联系方式]')

        body = f"""您好：

我是{recruiter}，看到您在{jd_info['direction_name']}方向的研究与实践，近期我这边正好有一个非常匹配您方向的岗位机会，想跟您聊聊看。

目前手头{jd_info['jd_company']}正在组建{jd_info['jd_team']}，具体JD如下：

【{jd_info['jd_title']}】
方向：{jd_info['tech_tags']}
职责：{jd_info['jd_duties']}
要求：{jd_info['jd_req']}
地点：{jd_info.get('jd_location', '面议')}
形式：全职/合作皆可

您的工作 "{jd_info['paper_title']}" 让我印象深刻，感觉与当前团队的需求高度契合。

此外，我这边也在持续关注本领域的前沿方向，无论您是看机会还是单纯想拓宽视野，都非常乐意多交流。

我能提供的：行业机会推荐、职业发展建议、行业趋势洞察、人脉资源链接

方便的话可以加个微信交流，我的微信：{wechat}

————————————————
{signature}"""

        # Retry logic: socket.create_connection is patched to use proxy CONNECT tunnel
        for attempt in range(3):
            try:
                msg = MIMEText(body, 'plain', 'utf-8')
                msg['From'] = self.config['email']
                msg['To'] = to_addr
                msg['Subject'] = Header(subject, 'utf-8')
                server = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=60)
                server.login(self.config['email'], self.config['password'])
                server.sendmail(self.config['email'], [to_addr], msg.as_string())
                server.quit()
                print(f"   [SEND] ✓ {author_name} <{to_addr}>")
                return True
            except Exception as ex:
                if attempt < 2:
                    print(f"   [SEND] ⏳ {author_name} <{to_addr}> retry {attempt+1}: {ex}")
                    time.sleep(8)
                else:
                    print(f"   [SEND] ✗ {author_name} <{to_addr}> (3 attempts failed): {ex}")
        return False


# ═══════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════

def generate_summary(results, run_date, total_found):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    sent = [r for r in results if r.get('emails_sent')]
    uncertain = [r for r in results if not r.get('emails_sent') and not r.get('skipped')]
    skipped = [r for r in results if r.get('skipped')]

    lines = []
    lines.append(f"# 🤖 机器人顶会论文推送小结 — {run_date}\n")
    lines.append(f"📅 执行时间：{now}\n")
    lines.append("---\n")
    lines.append("## 📊 今日概况\n")
    lines.append(f"- 发现匹配论文：**{total_found}** 篇")
    lines.append(f"- 本次处理：**{len(results)}** 篇（已发{sum(len(r.get('emails_sent', [])) for r in results)}封 | 未确定{len(uncertain)}篇 | 跳过{len(skipped)}篇无华人作者）\n")

    if sent:
        lines.append("---\n## ✅ 已发送邮件\n")
        for r in sent:
            lines.append(f"### 📄 {r['paper']['title'][:80]}")
            lines.append(f"- **方向**: {r.get('direction', '未知')}")
            lines.append(f"- **会议**: {r['paper'].get('venue', 'unknown')}")
            lines.append(f"- **作者**: {', '.join(r['paper']['authors'][:3])}")
            lines.append(f"- **发送给**:")
            for e in r['emails_sent']:
                lines.append(f"  - {e['name']} <{e['email']}>")
            lines.append(f"- **亮点**: {r.get('highlight', '相关方向的前沿工作')}\n")

    if uncertain:
        lines.append("---\n## ❓ 邮箱未确定（需手动处理）\n")
        for r in uncertain:
            lines.append(f"### 📄 {r['paper']['title'][:80]}")
            lines.append(f"- **方向**: {r.get('direction', '未知')}")
            lines.append(f"- **会议**: {r['paper'].get('venue', 'unknown')}")
            lines.append(f"- **作者**: {', '.join(r['paper']['authors'][:3])}")
            lines.append(f"- **arXiv**: {r['paper']['url']}\n")

    if skipped:
        lines.append("---\n## ⏭️ 跳过（无华人一作/二作）\n")
        for r in skipped:
            lines.append(f"### 📄 {r['paper']['title'][:80]}")
            lines.append(f"- **作者**: {', '.join(r['paper']['authors'][:3])}")
            lines.append(f"- **arXiv**: {r['paper']['url']}\n")

    lines.append("---\n## 📈 方向分布\n")
    dirs = {}
    for r in results:
        d = r.get('direction', '未知')
        dirs[d] = dirs.get(d, 0) + 1
    for d, c in sorted(dirs.items(), key=lambda x: -x[1]):
        lines.append(f"- {d}: {'█' * c} {c}篇")

    lines.append("\n---\n*自动执行于 Robot Paper Campaign v1.0*")
    return "\n".join(lines)


def extract_highlight(title, abstract):
    abs_low = abstract.lower()
    for m in ["state-of-the-art", "sota", "first", "novel", "achieve",
              "outperform", "best", "breakthrough", "significant"]:
        if m in abs_low:
            idx = abs_low.find(m)
            return abstract[max(0, idx-20):idx+80].strip()[:150]
    return "相关方向的前沿工作"


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════

def main():
    # Parse args
    max_papers = MAX_PAPERS_PER_RUN
    date_from_str = None
    dry_run = False
    venues_override = None
    categories_override = None
    no_prompt = False

    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == '--max-papers' and i+1 < len(args):
            max_papers = int(args[i+1])
        elif a == '--date-from' and i+1 < len(args):
            date_from_str = args[i+1]
        elif a == '--venues' and i+1 < len(args):
            venues_override = [v.strip() for v in args[i+1].split(',') if v.strip()]
        elif a == '--categories' and i+1 < len(args):
            categories_override = [c.strip() for c in args[i+1].split(',') if c.strip()]
        elif a == '--dry-run':
            dry_run = True
        elif a == '--no-prompt':
            no_prompt = True

    # ── 顶会 & arXiv 分类：用户自定义（启动前选择）──
    # 优先级：命令行参数 > 交互输入 > 默认常量
    venues = venues_override
    categories = categories_override
    if not no_prompt and sys.stdin.isatty():
        print("\n⚙️  本次推送配置（直接回车 = 使用默认）")
        try:
            v_in = input(f"  顶会关键词（默认: {', '.join(VENUE_KEYWORDS[:6])}...）: ").strip()
            if v_in:
                venues = [x.strip() for x in v_in.split(',') if x.strip()]
            c_in = input(f"  arXiv 分类（默认: {', '.join(ARXIV_CATEGORIES)}）: ").strip()
            if c_in:
                categories = [x.strip() for x in c_in.split(',') if x.strip()]
        except EOFError:
            pass
    venues = venues or VENUE_KEYWORDS
    categories = categories or ARXIV_CATEGORIES

    today = date.today()
    run_date = today.isoformat()
    date_from = date_from_str or (today - timedelta(days=3)).isoformat()
    date_to = today.isoformat()

    print(f"🤖 Robot Paper Campaign")
    print(f"📅 Range: {date_from} → {date_to} | Max: {max_papers} | {'DRY-RUN' if dry_run else 'LIVE'}")
    print(f"🏆 Venues: {', '.join(venues)}")
    print(f"📚 arXiv categories: {', '.join(categories)}\n")

    # Init DB
    tracker = PaperTracker(DB_PATH)

    # ── Step 1: arXiv Search ──
    print("🔍 Searching arXiv...")
    scraper = ArxivScraper()
    all_papers = scraper.search(venues, categories, date_from, date_to)
    print(f"\n   Total matching: {len(all_papers)} papers")

    # Filter by robotics relevance
    relevant = [p for p in all_papers if is_robotics_relevant(p)]
    print(f"   Robotics-relevant: {len(relevant)} papers (filtered out {len(all_papers)-len(relevant)})")

    # ── Step 2: Filter ──
    new_papers = [p for p in relevant if not tracker.is_processed(p['id'])]
    print(f"   Unprocessed: {len(new_papers)} papers")

    if not new_papers:
        print("   ✅ No new papers to process.")
        os.makedirs(SUMMARY_DIR, exist_ok=True)
        sp = os.path.join(SUMMARY_DIR, f"{run_date}.md")
        with open(sp, 'w') as f:
            f.write(f"# 🤖 机器人顶会论文推送小结 — {run_date}\n\n今日无新增匹配论文。\n📅 搜索范围: {date_from} → {date_to}\n")
        tracker.log_run(run_date, len(all_papers), 0, 0, 0, sp)
        print(f"📋 {sp}")
        return

    # ── Step 3: Process ──
    to_process = new_papers[:max_papers]
    print(f"\n📝 Processing {len(to_process)} papers...\n")

    finder = EmailFinder()
    jd_gen = JDGenerator()
    sender = EmailSender() if not dry_run else None

    results = []

    for idx, paper in enumerate(to_process):
        print(f"[{idx+1}/{len(to_process)}] {paper['title'][:70]}...")

        # Classify & JD
        direction = jd_gen.classify(paper['title'], paper['abstract'])
        jd_info = jd_gen.generate(direction, paper)
        highlight = extract_highlight(paper['title'], paper['abstract'])
        print(f"   → {direction['name']}")

        # Find emails for first and second authors (Chinese only)
        target_authors = [a for a in paper['authors'][:2] if is_chinese_name(a)]
        skipped_no_chinese = len(target_authors) == 0
        if skipped_no_chinese:
            print(f"   ⏭️ No Chinese authors in top 2, skipping paper")
        emails_sent = []

        for author in target_authors:
            print(f"   🔍 Looking up {author}...")
            paper_data = {
                'abstract': paper.get('abstract', ''),
                'comment': paper.get('comment', ''),
                'url': paper.get('url', ''),
            }
            email = finder.find_email(author, paper['title'], paper_data=paper_data)
            if email and not dry_run:
                ok = sender.send(email, author, jd_info)
                if ok:
                    emails_sent.append({'name': author, 'email': email})
                time.sleep(2)
            elif email and dry_run:
                print(f"   [DRY] Would send to {author} <{email}>")
                emails_sent.append({'name': author, 'email': email})
            elif dry_run:
                print(f"   [DRY] Email not found for {author}")

        results.append({
            'paper': paper, 'direction': direction['name'],
            'emails_sent': emails_sent, 'highlight': highlight,
            'skipped': skipped_no_chinese,
        })

        # Track
        fa = paper['authors'][0] if paper['authors'] else ''
        sa = paper['authors'][1] if len(paper['authors']) > 1 else ''
        sent_json = json.dumps(emails_sent) if emails_sent else ''
        tracker.mark_processed(paper['id'], paper['title'], paper.get('venue', ''),
                               fa, sa, direction['name'], sent_json, highlight)

    # ── Step 4: Summary ──
    print("\n📋 Writing summary...")
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    summary_text = generate_summary(results, run_date, len(all_papers))
    summary_path = os.path.join(SUMMARY_DIR, f"{run_date}.md")
    with open(summary_path, 'w') as f:
        f.write(summary_text)

    total_sent = sum(len(r.get('emails_sent', [])) for r in results)
    uncertain = len([r for r in results if not r.get('emails_sent')])
    tracker.log_run(run_date, len(all_papers), len(results), total_sent, uncertain, summary_path)

    print(f"\n{'='*50}")
    print(f"✅ Done!")
    print(f"   Found: {len(all_papers)} | Processed: {len(results)}")
    print(f"   Emails sent: {total_sent} | Uncertain: {uncertain}")
    print(f"   Summary: {summary_path}")
    print(f"{'='*50}")

    # Print summary to stdout for automation capture
    print("\n\n=== SUMMARY START ===")
    print(summary_text)
    print("=== SUMMARY END ===")


if __name__ == '__main__':
    print(AUTHOR_EPILOG, file=sys.stderr)
    main()
