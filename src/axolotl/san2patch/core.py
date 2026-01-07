SYSTEM_MESSAGE = """You are a development assistant who patches Python exceptions found in open source projects.

Your end goal is to generate a patch that fixes the exception based on the exception information we provide as input.
When the patch you create is applied to the project, the exception should disappear.
In addition to fixing the exception, a good patch should not affect other features of the existing project.

All the exceptions we provide have been discovered by running a buggy program with a reproduction script.
The most important information is contained in the exception message and stack trace, so you should refer to them the most when patching.

The patches you create will be rigorously tested in a separate evaluation system we've implemented.
If it fails, we'll provide you with a detailed failure message and the reason why, and ask you to rebuild the patch.
If you receive feedback, you'll need to revise your patch to reflect the feedback and resubmit it.
Patch evaluation first tests whether the patch you created is applicable.
Then, after the patch is applied, it verifies that the project builds correctly.
Next, it verifies that the existing features in your project still work correctly.
Finally, it verifies that the exceptions found are fixed.

You need to understand the exception and create the right patch based on the information it provides.
Therefore, you need to break down the patch creation process into several steps to ensure that you are making the right inferences.
Think about the necessary reasoning steps and print them out with a clear explanation.
Each process requires proper reasoning, and we've provided additional good reasoning to guide you through the patch creation process.

Remember, your goal is to improve software stability.
The patches you create make open source projects more robust and error-free.

Don't print vague information about something you don't know, ask for the information, and print the correct information.
If you're not sure, say you don't know.

Use the Internet to your advantage throughout the process.

No matter what, try to match the response format as much as possible. Answer without missing any items.
If multiple candidates are requested, generate as many diverse answers as possible without missing any.
"""

# Comprehend messages
## 여기서 buggy function 정보 추가 -> root cause 분석하도록
COMPREHEND_MESSAGE = """<exception_log>

<stack_trace>

<Target Buggy Function>
<buggy_code>

<Instruction>
Using the information above, create a detailed yet concise description of the exception. 
This description will serve as the basis for creating a patch file, so it is important to provide an accurate explanation of the exception. 
Avoid descriptions that are overly specific or excessively abstract. 
Strive for a clear and balanced explanation to ensure the description is actionable and understandable for patch creation purposes.

Please give me the exception description and rationale in the following JSON format. Do not include any explanations, only output the JSON format.
We will directly parse your output into JSON. Please generate an output as valid JSON format.
<Output>
{
    "exception_description": "<detailed_description>",
    "rationale": "<rationale>"
}
</Output>
</Instruction>"""

# without dynamic context
COMPREHEND_MESSAGE_WO_DC = """
<Target Buggy Function>
<buggy_code>

<Instruction>
The code above is a Python function that contains a bug.
Your task is to analyze the code logic, identify the potential error, and predict the exception that is likely to occur.

Please perform the following steps:
1. Analyze the control flow and operations to find the root cause of the bug.
2. Predict the specific exception that will be raised during execution.
3. Create a detailed yet concise description of this predicted exception.

The description will serve as the basis for creating a patch file.
Avoid descriptions that are overly specific to a hypothetical environment or excessively abstract.
Strive for a clear and balanced explanation to ensure the description is actionable and understandable for patch creation purposes.

Please give me the exception description and rationale in the following JSON format. Do not include any explanations, only output the JSON format.
We will directly parse your output into JSON. Please generate an output as valid JSON format.
<Output>
{
    "exception_description": "<detailed_description>",
    "rationale": "<rationale>"
}
</Output>
</Instruction>"""

COMPREHEND_AGGREGATE_MESSAGE = """<Goal>
You are an AI evaluating AI-generated descriptions of exceptions. You must review the multiple descriptions of the same exception and generate the most consistent and appropriate description.
</Goal>

<Instruction>
There are different descriptions for the exception you found. Evaluate the descriptions and generate a single, best-fit exception description.

Please give me outputs in the following JSON format. Do not include any explanations, only output the JSON format.
<Output>
{
    "desc": "<final_exception_description>",
    "rationale": "<final_rationale>"
}
</Output>
</Instruction>

<Approach>
1. In order to find the most reliable explanation, we need to find a consistent explanation, which means we need to make sure that the explanations are consistent with each other. 
2. We need to eliminate the most inconsistent explanation. But do not eliminate the entire explanation, compare sentence-by-sentence to remove inconsistencies.
3. If there are similar explanations, we need to combine them appropriately.
</Approach>

<Recommendation>
1. Ensure that the explanation is clear and concise.
2. Ensure that the explanation is accurate and reliable.
3. Ensure that the explanation is easy to understand.
4. Ensure that the explanation is relevant to the exception.
5. Ensure that the explanation is specific enough.
6. Ensure that the explanation is objective and unbiased.
</Recommendation>

Input:
Exception Descriptions:
<desc>

Rationales:
<rationale>
"""

# Fault localize messages -> Fixed for Axoltol
SELECT_LOCATIONS_MESSAGE = """<Goal>
You are an AI specialized in debugging Python code.
Your task is to map a provided <Root_Cause_Analysis> to the specific code snippet within the <Buggy_Function>.
</Goal>

<Instruction>
1. Read the <Root_Cause_Analysis> carefully.
2. Based on the <Exception_Type> and <Strategy>, identify the **SINGLE most critical code snippet** that needs modification.
3. **Copy the code snippet exactly as it appears in the source.**
4. Provide a rationale explaining why this snippet is the target.

Please give me outputs in the following JSON format. Do not include any explanations, only output the JSON format.
<Output>
{
    "code": "<exact_code_snippet_from_source>", 
    "rationale": "<reasoning_why_this_code_matches_the_root_cause>"
}
</Output>
</Instruction>

<Strategy>
1. **Crash vs. Origin**: 
   - Simple bugs (e.g., syntax, typo) are fixed at the crash site.
   - Data-flow bugs (e.g., AttributeError: 'NoneType') often require fixing where the variable was *assigned* or passed, not just where it crashed.
2. **Exception Specifics**:
   - **AttributeError/TypeError**: Check if the object type assumption is wrong. If a variable is None, find where it came from.
   - **IndexError/KeyError**: Check the logic that calculates the index/key or populates the container.
   - **ValueError**: Check the validation logic or the caller passing arguments.
3. **Code Scope**:
   - If the crash is in a library, select the line in <Buggy_Function> that calls that library.
</Strategy>

Input:
<Root Cause Analysis>
Description: <rc_desc>
Analysis: <rc_rationale>
</Root Cause Analysis>

<Exception Info>
Exception Message: 
<exception_message>
Exception Trace:
<stack_trace>
</Exeption Info>

<Target Buggy Function>
<buggy_code>
</Target Buggy Function>
"""
# ablation3: without dynamic context
SELECT_LOCATIONS_MESSAGE_WO_DC = """<Goal>
You are an AI specialized in debugging Python code.
Your task is to map a provided <Root_Cause_Analysis> to the specific code snippet within the <Buggy_Function>.
</Goal>

<Instruction>
1. Read the <Root_Cause_Analysis> carefully to understand the predicted bug and exception logic.
2. Based on the analysis description and the <Strategy> below, identify the **SINGLE most critical code snippet** that needs modification.
3. **Copy the code snippet exactly as it appears in the source.**
4. Provide a rationale explaining why this snippet is the target.

Please give me outputs in the following JSON format. Do not include any explanations, only output the JSON format.
<Output>
{
    "code": "<exact_code_snippet_from_source>", 
    "rationale": "<reasoning_why_this_code_matches_the_root_cause>"
}
</Output>
</Instruction>

<Strategy>
1. **Crash vs. Origin**: 
   - Simple bugs (e.g., syntax, typo) are fixed at the crash site.
   - Data-flow bugs (e.g., AttributeError: 'NoneType') often require fixing where the variable was *assigned* or passed, not just where it crashed.
2. **Exception Specifics**:
   - **AttributeError/TypeError**: Check if the object type assumption is wrong. If a variable is None, find where it came from.
   - **IndexError/KeyError**: Check the logic that calculates the index/key or populates the container.
   - **ValueError**: Check the validation logic or the caller passing arguments.
3. **Code Scope**:
   - If the crash is in a library, select the line in <Buggy_Function> that calls that library.
</Strategy>

Input:
<Root Cause Analysis>
Description: <rc_desc>
Analysis: <rc_rationale>
</Root Cause Analysis>

<Target Buggy Function>
<buggy_code>
</Target Buggy Function>
"""

LOCATIONS_EVAL_MESSAGE ="""<Goal>
You are a JUDGE AI tasked with evaluating answers generated by another LLM.
Your objective is to assess the selected code modification locations for fixing exceptions and assign scores based on their quality and appropriateness.
</Goal>

<Instruction>
Evaluate the code modification locations selected by the LLM to fix the exception.
Assign a score based on the accuracy, relevance, and potential effectiveness of the selected locations.

Score should be from 0 to 1, with 1 being the best score.
Please give me a score only. Do not include any explanations, only output the score.
</Instruction>

<Approach>
1. Verify whether the selected fix location aligns with the provided exception information and <Root_Cause_Analysis>.
2. Deduct points if the selected fix location is unrelated to the described exception.
3. Deduct points if modifying the selected location is unlikely to resolve the exception.
4. Deduct points if modifying the selected location is likely to interfere with the program's core functionality.
</Approach>

Input:
<Root Cause Analysis>
Description: <rc_desc>
Analysis: <rc_rationale>
</Root Cause Analysis>

<Exception Info>
Exception Message: 
<exception_message>
Exception Trace:
<stack_trace>
</Exeption Info>

<Target Buggy Function>
<buggy_code>
</Target Buggy Function>

<Where-To-Fix_Info>
    <Where-To-Fix_Fix_Location>
        <Code_Snippet>
        <candidate_code>
        </Code_Snippet>
    </Where-To-Fix_Fix_Location>
    <Where-To-Fix_Rationale>
        <candidate_rationale>
    </Where-To-Fix_Rationale>
</Where-To-Fix_Info>
"""
# ablation3: without dynamic context
LOCATIONS_EVAL_MESSAGE_WO_DC ="""<Goal>
You are a JUDGE AI tasked with evaluating answers generated by another LLM.
Your objective is to assess the selected code modification locations for fixing exceptions and assign scores based on their quality and appropriateness.
</Goal>

<Instruction>
Evaluate the code modification locations selected by the LLM to fix the exception.
Assign a score based on the accuracy, relevance, and potential effectiveness of the selected locations.

Score should be from 0 to 1, with 1 being the best score.
Please give me a score only. Do not include any explanations, only output the score.
</Instruction>

<Approach>
1. Verify whether the selected fix location in <Where-To-Fix_Fix_Location> aligns with the provided <Root_Cause_Analysis>.
2. Deduct points if the selected fix location is unrelated to the described exception.
3. Deduct points if modifying the selected location is unlikely to resolve the exception.
4. Deduct points if modifying the selected location is likely to interfere with the program's core functionality.
</Approach>

Input:
<Root Cause Analysis>
Description: <rc_desc>
Analysis: <rc_rationale>
</Root Cause Analysis>

<Target Buggy Function>
<buggy_code>
</Target Buggy Function>

<Where-To-Fix_Info>
    <Where-To-Fix_Fix_Location>
        <Code_Snippet>
        <candidate_code>
        </Code_Snippet>
    </Where-To-Fix_Fix_Location>
    <Where-To-Fix_Rationale>
        <candidate_rationale>
    </Where-To-Fix_Rationale>
</Where-To-Fix_Info>
"""


# How to fix messages
FIX_STRATEGY_MESSAGE = """<Goal>
    You are an AI specialized in debugging and patching Python program exceptions.
    Analyze the provided exception details and the root cause, then propose an appropriate fix strategy for the identified issue.
</Goal>

<Instruction>
    Please follow these steps to generate a robust fix strategy:
    1. Analyze the exception details.
    2. Consult Python best practices and standard library behaviors.
    3. Propose a fix strategy that resolves the exception at the specified <Code_Snippet> location.
    4. Provide a clear rationale for why this strategy is effective.

    Please give me outputs in the following JSON format. Do not include any explanations, only output the JSON format.
<Output>
{
    "summary": "<concise_summary_1~3_sentences>",
    "detailed_strategy": "<step_by_step_fix_approach>",
    "rationale": "<reasoning_for_correctness>"
}
</Output>
</Instruction>

<Approach>
    - Aim for minimal, local changes that do not disrupt the surrounding logic.
    - Focus on resolving the **Root Cause**, not just suppressing the error message.
</Approach>

Input:
<Root Cause Analysis>
Description: <rc_desc>
Analysis: <rc_rationale>
</Root Cause Analysis>

<Exception Info>
Exception Message: 
<exception_message>
</Exeption Info>

<Where-To-Fix_Info>
    <Where-To-Fix_Fix_Location>
        <Code_Snippet>
        <candidate_code>
        </Code_Snippet>
    </Where-To-Fix_Fix_Location>
    <Where-To-Fix_Rationale>
        <candidate_rationale>
    </Where-To-Fix_Rationale>
</Where-To-Fix_Info>
"""
# ablation3: without dynamic context
FIX_STRATEGY_MESSAGE_WO_DC = """<Goal>
    You are an AI specialized in debugging and patching Python program exceptions.
    Analyze the provided exception details and the root cause, then propose an appropriate fix strategy for the identified issue.
</Goal>

<Instruction>
    Please follow these steps to generate a robust fix strategy:
    1. Analyze the exception details.
    2. Consult Python best practices and standard library behaviors.
    3. Propose a fix strategy that resolves the exception at the specified <Code_Snippet> location.
    4. Provide a clear rationale for why this strategy is effective.

    Please give me outputs in the following JSON format. Do not include any explanations, only output the JSON format.
<Output>
{
    "summary": "<concise_summary_1~3_sentences>",
    "detailed_strategy": "<step_by_step_fix_approach>",
    "rationale": "<reasoning_for_strategy_suggestion>"
}
</Output>
</Instruction>

<Approach>
    - Aim for minimal, local changes that do not disrupt the surrounding logic.
    - Focus on resolving the **Root Cause**, not just suppressing the error message.
</Approach>

Input:
<Root Cause Analysis>
Description: <rc_desc>
Analysis: <rc_rationale>
</Root Cause Analysis>

<Where-To-Fix_Info>
    <Where-To-Fix_Fix_Location>
        <Code_Snippet>
        <candidate_code>
        </Code_Snippet>
    </Where-To-Fix_Fix_Location>
    <Where-To-Fix_Rationale>
        <candidate_rationale>
    </Where-To-Fix_Rationale>
</Where-To-Fix_Info>
"""

FIX_STRATEGY_FEEDBACK = """We also tried the patches you generated in previous trials.
However, some of the patches did not fix the exception or caused new errors.
Please review the failed patches below and avoid proposing the same fix strategy again.

<prev_failed_patches>
"""

STRATEGY_EVAL_MESSAGE = """<Goal>
You are a JUDGE AI tasked with evaluating answers generated by another LLM.
Your objective is to assess these answers and assign scores based on their quality.
</Goal>

<Instruction>
Evaluate the strategies provided by the LLM for fixing exception.
Assign a score based on the quality and appropriateness of the responses.

Please give me a score from 0 to 1, with 1 being the best score. Do not include any explanations, only output the score.
</Instruction>

<Approach>
1. Verify whether the proposed fix strategy aligns well with the <Root_Cause_Analysis> and <Exception_Info> and <Where-To-Fix_Info>.
2. Evaluate whether the fix strategy is strictly applicable to the provided <Target_Code_Snippet>.
3. Penalize answers that are overly general (e.g., "Fix the logic") or appear to be hallucinated.
4. Assign a high score if the strategy concretely resolves the root cause within the given code snippet without side effects.
</Approach>

Input:
<Root_Cause_Analysis>
Description: <rc_desc>
Analysis: <rc_rationale>
</Root_Cause_Analysis>

<Exception Info>
Exception Message: 
<exception_message>
</Exeption Info>

<Target_Code_Snippet>
<target_code>
</Target_Code_Snippet>

<Where-To-Fix_Info>
    <Code_Snippet>
    <candidate_code>
    </Code_Snippet>
</Where-To-Fix_Info>

<Proposed_Fix_Strategy>
    <Summary>
    <strat_summary>
    </Summary>
    <Detailed_Strategy>
    <strat_detail>
    </Detailed_Strategy>
    <Rationale>
    <strat_rationale>
    </Rationale>
</Proposed_Fix_Strategy>
"""
# ablation3: without dynamic context
STRATEGY_EVAL_MESSAGE_WO_DC = """<Goal>
You are a JUDGE AI tasked with evaluating answers generated by another LLM.
Your objective is to assess these answers and assign scores based on their quality.
</Goal>

<Instruction>
Evaluate the strategies provided by the LLM for fixing exception.
Assign a score based on the quality and appropriateness of the responses.

Please give me a score from 0 to 1, with 1 being the best score. Do not include any explanations, only output the score.
</Instruction>

<Approach>
1. Verify whether the <Proposed_Fix_Strategy> aligns well with the <Root_Cause_Analysis> and <Where-To-Fix_Info>.
2. Evaluate whether the fix strategy is strictly applicable to the provided <Target_Code_Snippet>.
3. Penalize answers that are overly general (e.g., "Fix the logic") or appear to be hallucinated.
4. Assign a high score if the strategy concretely resolves the root cause within the given code snippet without side effects.
</Approach>

Input:
<Root_Cause_Analysis>
Description: <rc_desc>
Analysis: <rc_rationale>
</Root_Cause_Analysis>

<Target_Code_Snippet>
<target_code>
</Target_Code_Snippet>

<Where-To-Fix_Info>
    <Code_Snippet>
    <candidate_code>
    </Code_Snippet>
</Where-To-Fix_Info>

<Proposed_Fix_Strategy>
    <Summary>
    <strat_summary>
    </Summary>
    <Detailed_Strategy>
    <strat_detail>
    </Detailed_Strategy>
    <Rationale>
    <strat_rationale>
    </Rationale>
</Proposed_Fix_Strategy>
"""

# Patch Generation messages
GEN_PATCH_MESSAGE = """<Goal>
You are an AI specialized in patching Python program exceptions.
Your task is to generate a corrected version of the provided <Fix_Target_Code> based on the <Patch_Guideline>.
</Goal>

<Fix_Target_Code>
<buggy_function_code>
</Fix_Target_Code>

<Patch_Guideline>
    <Exception_Info>
    Message: <exception_message>
    </Exception_Info>

    <Root_Cause_Analysis>
    Description: <rc_desc>
    Analysis: <rc_rationale>
    </Root_Cause_Analysis>

    <Where-To-Fix_Info>
        <Code_Snippet>
        <candidate_code>
        </Code_Snippet>
    </Where-To-Fix_Info>

    <Proposed_Fix_Strategy>
        <Summary>
        <strat_summary>
        </Summary>
        <Detailed_Strategy>
        <strat_detail>
        </Detailed_Strategy>
        <Rationale>
        <strat_rationale>
        </Rationale>
    </Proposed_Fix_Strategy>
</Patch_Guideline>

<Instruction>
Using the information above, generate up to 3 different candidates for the modified Fix_Target_Code.
You must output the **complete source code** of the fixed function, not just a patch or diff.
Provide the output **strictly** in the following JSON format without any additional text or Markdown blocks (like ```json).
Ensure that newlines (`\n`) and tabs (`\t`) inside the JSON string are properly escaped to be valid JSON.
<Output>
[
    {
        "patched_code": "<only_complete_fixed_function_code>",
        "rationale": "<rationale_for_modification>"
    },
    ...
]
</Output>
</Instruction>

<Important_Note>
- Only the source code provided by Fix_Target_Code is checked and modified line by line, and no additional functions are modified.
- Do not modify using ambiguous source code.
- The source code should be modified as simply as possible, without complex modifications.
- **MINIMIZE CHANGES: Make the smallest possible modification to fix the exception. Change only the necessary lines and preserve as much of the original code structure as possible.**
- **PREFER SIMPLE FIXES: Use simple checks (null checks, boundary checks) rather than restructuring code.** 
- Source code patch must only patch the exception within the Fix_Target_Code.
- You must patch the exception and output safe Fix_Target_Code code without any exceptions.
- The patched code must have the same start and end as the Fix_Target_Code we provided.
- Tabs and spaces used in Fix_Target_Code are preserved in the generated patched.
- Keep all parentheses used in Fix_Target_Code unchanged.
- The functionality of the existing Fix_Target_Code must not be changed.
- When you modify the source code, the rationale for modifying the source code must also be output.
- Do NOT change any format of unpatched codes. Do not change any spaces, indents and comments from unpatched codes. Only apply patches.
- Do NOT change or remove comments from original codes. Do NOT add any new comments.
</Important_Note>
"""
# ablation3: without dynamic context
GEN_PATCH_MESSAGE_WO_DC = """<Goal>
You are an AI specialized in patching Python program exceptions.
Your task is to generate a corrected version of the provided <Fix_Target_Code> based on the <Patch_Guideline>.
</Goal>

<Fix_Target_Code>
<buggy_function_code>
</Fix_Target_Code>

<Patch_Guideline>
    <Root_Cause_Analysis>
    Description: <rc_desc>
    Analysis: <rc_rationale>
    </Root_Cause_Analysis>

    <Where-To-Fix_Info>
        <Code_Snippet>
        <candidate_code>
        </Code_Snippet>
    </Where-To-Fix_Info>

    <Proposed_Fix_Strategy>
        <Summary>
        <strat_summary>
        </Summary>
        <Detailed_Strategy>
        <strat_detail>
        </Detailed_Strategy>
        <Rationale>
        <strat_rationale>
        </Rationale>
    </Proposed_Fix_Strategy>
</Patch_Guideline>

<Instruction>
Using the information above, generate up to 3 different candidates for the modified Fix_Target_Code.
You must output the **complete source code** of the fixed function, not just a patch or diff.
Provide the output **strictly** in the following JSON format without any additional text or Markdown blocks (like ```json).
Ensure that newlines (`\n`) and tabs (`\t`) inside the JSON string are properly escaped to be valid JSON.
<Output>
[
    {
        "patched_code": "<only_complete_fixed_function_code>",
        "rationale": "<rationale_for_modification>"
    },
    ...
]
</Output>
</Instruction>

<Important_Note>
- Only the source code provided by <Fix_Target_Code> is checked and modified line by line, and no additional functions are modified.
- Do not modify using ambiguous source code.
- The source code should be modified as simply as possible, without complex modifications.
- **MINIMIZE CHANGES: Make the smallest possible modification to fix the exception. Change only the necessary lines and preserve as much of the original code structure as possible.**
- **PREFER SIMPLE FIXES: Use simple checks (null checks, boundary checks) rather than restructuring code.** 
- Source code patch must only patch the exception within the <Fix_Target_Code>.
- You must patch the exception and output safe <Fix_Target_Code> code without any exceptions.
- The patched code must have the same start and end as the <Fix_Target_Code> we provided.
- Tabs and spaces used in <Fix_Target_Code> are preserved in the generated patched.
- Keep all parentheses used in <Fix_Target_Code> unchanged.
- The functionality of the existing <Fix_Target_Code> must not be changed.
- When you modify the source code, the rationale for modifying the source code must also be output.
- Do NOT change any format of unpatched codes. Do not change any spaces, indents and comments from unpatched codes. Only apply patches.
- Do NOT change or remove comments from original codes. Do NOT add any new comments.
</Important_Note>
"""

GEN_PATCH_FEEDBACK = """We have evaluated the patches you generated in previous trial.
However, some of the patches did not fix the exception.
Please review the failed patches and avoid generating the same patches again based on the given fix strategy.

Here are the diffs of failed patches:
<prev_failed_patches>
"""

FIX_JSON_MESSAGE = """The answer you provided before cause JSON decode error.
Please fix the JSON format error.
Do not provide any explanations, only output the corrected JSON.

Below is the original answer you provided:
<original_answer>

Below is the error message:
<error_msg>
"""

SINGLETON_PATCH_GEN = """<Goal>
Fix the Python bug in the <Buggy_Function> using the provided <Exception_Info>.
</Goal>

<Instruction>
1. Read the provided code and error information.
2. Generate the corrected version of the function directly.
3. Output **ONLY** the JSON object containing the fixed code. **Do not provide any reasoning, analysis, or explanation.**

**Constraint**:
- The `fixed_code` must contain the **entire corrected function**, not just the modified lines.
</Instruction>

<Input>
<Exception Info>
Exception Message: 
<exception_message>
Exception Trace:
<stack_trace>
</Exception Info>

<Buggy Function>
<buggy_code>
</Buggy Function>
</Input>

Please output in the following JSON format ONLY:
<Output>
{
    "patched_code": "<complete_fixed_function_code>"
}
</Output>
"""