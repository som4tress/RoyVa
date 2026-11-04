// Estimate from observed model latency, not task words or device names.
export function localContinuationEstimate({startedAt,now=Date.now(),lastModelMs,budgetMs=60000}){
 const remainingMs=budgetMs-(now-startedAt);
 if(!(lastModelMs>0))return {escalate:remainingMs<=0,remainingMs,estimatedNextMs:null};
 const estimatedNextMs=lastModelMs;
 return {escalate:remainingMs<=0||estimatedNextMs>remainingMs+10000,remainingMs,estimatedNextMs};
}
