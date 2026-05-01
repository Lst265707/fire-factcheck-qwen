import dataclasses
from typing import Any
from common import modeling, shared_config, utils
from eval.fire import config as fire_config
from eval.fire import query_serper
from eval.fire.query_serper import SerperAPI

_Factual_LABEL = 'True'
_Non_Factual_LABEL = 'False'
_STATEMENT_PLACEHOLDER = '[STATEMENT]'
_KNOWLEDGE_PLACEHOLDER = '[KNOWLEDGE]'


_FINAL_ANSWER_OR_NEXT_SEARCH_FORMAT = f"""\
Instructions:
1. You are provided with a STATEMENT and relevant KNOWLEDGE points.
2. Based on the KNOWLEDGE, assess the factual accuracy of the STATEMENT.
3. Before presenting your conclusion, think through the process step-by-step. 
   Include a summary of the key points from the KNOWLEDGE as part of your reasoning.
4. If the KNOWLEDGE allows you to confidently make a decision, output the final 
   answer as a JSON object in the following format:
   {{
     "final_answer": "{_Factual_LABEL}" or "{_Non_Factual_LABEL}"
   }}
5. If the KNOWLEDGE is insufficient to make a judgment, issue ONE Google Search 
   query that could provide additional evidence. Output the search query in JSON 
   format, as follows:
   {{
     "search_query": "Your Google search query here"
   }}
6. The query should aim to obtain new information not already present in the 
   KNOWLEDGE, specifically helpful for verifying the STATEMENT's accuracy.

KNOWLEDGE:
{_KNOWLEDGE_PLACEHOLDER}

STATEMENT:
{_STATEMENT_PLACEHOLDER}
"""


_MUST_HAVE_FINAL_ANSWER_FORMAT = f"""\
Instructions:
1. You are provided with a STATEMENT and relevant KNOWLEDGE points.
2. Based on the KNOWLEDGE, assess the factual accuracy of the STATEMENT.
3. Before presenting your final answer, think step-by-step and show your reasoning. 
   Include a summary of the key points from the KNOWLEDGE as part of your reasoning.
4. Your final answer should be either "{_Factual_LABEL}" or "{_Non_Factual_LABEL}".
5. Format your final answer as a JSON object in the following structure:
   {{
     "final_answer": "{_Factual_LABEL}" or "{_Non_Factual_LABEL}"
   }}

KNOWLEDGE:
{_KNOWLEDGE_PLACEHOLDER}

STATEMENT:
{_STATEMENT_PLACEHOLDER}
"""


@dataclasses.dataclass()
class GoogleSearchResult:
    query: str
    result: str


@dataclasses.dataclass()
class FinalAnswer:
    response: str
    answer: str


def call_search(
        search_query: str,
        search_type: str = fire_config.search_type,
        num_searches: int = fire_config.num_searches,
        serper_api_key: str = shared_config.serper_api_key,
        search_postamble: str = '',
) -> str:
    """Call Google Search to get the search result."""
    search_query += f' {search_postamble}' if search_postamble else ''

    if search_type == 'serper':
        serper_searcher = query_serper.SerperAPI(serper_api_key, k=num_searches)
        return serper_searcher.run(search_query, k=num_searches)
    else:
        raise ValueError(f'Unsupported search type: {search_type}')


def final_answer_or_next_search(
        atomic_claim: str,
        past_searches: list[GoogleSearchResult],
        model: modeling.Model,
) -> tuple[FinalAnswer | GoogleSearchResult | None | str, dict | None]:
    knowledge = '\n'.join([s.result for s in past_searches])
    knowledge = 'N/A' if not knowledge else knowledge
    full_prompt = _FINAL_ANSWER_OR_NEXT_SEARCH_FORMAT.replace(_STATEMENT_PLACEHOLDER, atomic_claim)
    full_prompt = full_prompt.replace(_KNOWLEDGE_PLACEHOLDER, knowledge)
    full_prompt = utils.strip_string(full_prompt)

    model_response, usage = model.generate(full_prompt)

    answer_or_next_query = utils.extract_json_from_output(model_response)
    if answer_or_next_query is None:
        return None, None
    elif 'final_answer' in answer_or_next_query:
        return FinalAnswer(response=model_response, answer=answer_or_next_query['final_answer']), usage
    elif 'search_query' in answer_or_next_query:
        return GoogleSearchResult(query=answer_or_next_query['search_query'], result=call_search(answer_or_next_query['search_query'])), usage
    else:
        print(f"Unexpected output: {answer_or_next_query}")
        return None, None


def must_get_final_answer(
        atomic_fact: str,
        searches: list[GoogleSearchResult],
        model: modeling.Model,
) -> tuple[FinalAnswer | None, dict | None]:
    knowledge = '\n'.join([search.result for search in searches])
    full_prompt = _MUST_HAVE_FINAL_ANSWER_FORMAT.replace(
        _STATEMENT_PLACEHOLDER, atomic_fact
    )
    full_prompt = full_prompt.replace(_KNOWLEDGE_PLACEHOLDER, knowledge)
    full_prompt = utils.strip_string(full_prompt)

    try:
        model_response, usage = model.generate(full_prompt)
        if not model_response:
            return None, None

        answer = utils.extract_json_from_output(model_response)
        if not answer:
            return None, None

        if 'final_answer' in answer:
            final_answer = answer['final_answer']

        if final_answer in [_Factual_LABEL, _Non_Factual_LABEL]:
            return FinalAnswer(response=model_response, answer=final_answer), usage
        else:
            return None, None
    except Exception as e:
        print(f"Error in must_get_final_answer: {e}")
        return None, None


def verify_atomic_claim(
        atomic_claim: str,
        rater: modeling.Model,
        max_steps: int = fire_config.max_steps,
        max_retries: int = fire_config.max_retries,
) -> tuple[FinalAnswer | None, dict[str, Any], dict | None]:
    print("✅ 当前使用的模型：", rater.organization, rater.model_id)

    search_results = []
    total_usage = {
        'input_tokens': 0,
        'output_tokens': 0,
    }

    for _ in range(max_steps):
        answer_or_next_search, num_tries = None, 0
        while not answer_or_next_search and num_tries <= max_retries:
            answer_or_next_search, usage = final_answer_or_next_search(atomic_claim, search_results, rater)
            if usage is not None:
                total_usage['input_tokens'] += usage['input_tokens']
                total_usage['output_tokens'] += usage['output_tokens']
            num_tries += 1

        if answer_or_next_search is None:
            print(f'Maximum tryouts passed, still no answer or next search found.')
            break
        elif isinstance(answer_or_next_search, GoogleSearchResult):
            search_results.append(answer_or_next_search)
        elif isinstance(answer_or_next_search, FinalAnswer):
            search_dicts = {
                'google_searches': [dataclasses.asdict(s) for s in search_results]
            }
            return answer_or_next_search, search_dicts, total_usage

    final_answer, num_tries = None, 0
    while not final_answer and num_tries <= max_retries:
        num_tries += 1
        final_answer, usage = must_get_final_answer(atomic_claim, searches=search_results, model=rater)
        if usage is not None:
            total_usage['input_tokens'] += usage['input_tokens']
            total_usage['output_tokens'] += usage['output_tokens']

    search_dicts = {
        'google_searches': [dataclasses.asdict(s) for s in search_results]
    }
    return final_answer, search_dicts, total_usage


if __name__ == '__main__':
    pass