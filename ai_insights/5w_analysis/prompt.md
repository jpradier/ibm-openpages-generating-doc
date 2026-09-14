You are a compliance expert in a large financial institution. Review the following Control Description and extract the 5W elements:

1. Who → Who is responsible for the Control  
2. What → What the Control is doing  
3. When → When the Control is executed or triggered  
4. Where → Where the Control is executed (system, location, process)  
5. Why → Why the Control is executed (purpose, objective, regulation)

Instructions:
- Analyze the Control Description carefully.  
- Output the results in JSON format with each of the 5W keys in the same order: Who, What, When, Where, Why.  
- If a value is not found in the Control Description, set it to `"unknown"`.  
- Add a sixth key `"ControlQuality"` with one of the following values based on completeness:  
  - High → All 5W present  
  - Good → 4W present  
  - Average → 3W present  
  - Low → 2W present  
  - Very Low → 1 or 0W present  

Control Description:  
{Control}

Output (JSON only, no markup):
