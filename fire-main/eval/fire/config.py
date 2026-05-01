
"""Specific configuration for the FIRE framewrok."""

from common import shared_config

################################################################################
#                              SEARCH SETTINGS
# search_type: str = Google Search API used. Choose from ['serper'].
# num_searches: int = Number of results to show per search.
################################################################################
search_type = 'serper'
num_searches = 3 #每次搜索只取前 3 条最相关的结果

################################################################################
#                               FIRE SETTINGS
# max_steps: int = maximum number of break-down steps for factuality check.
# max_retries: int = maximum number of retries when fact checking fails.
# max_tolerance: int = maximum number of repetitive searches when fact checking.
# diverse_prompt: bool = whether to use diverse prompts for fact checking.
################################################################################
max_steps = 5 #把一条新闻最多拆成 5 个小事实去核查
max_retries = 10 #如果验证失败，最多重试 10 次
max_tolerance = 2 #最多允许 2 次重复搜索
diverse_prompt = False
# 是否使用多样化提示词
# False = 用固定的提示词（稳定、效果一致）
# True = 用多种不同的提示词（可能更鲁棒，但容易不稳定）