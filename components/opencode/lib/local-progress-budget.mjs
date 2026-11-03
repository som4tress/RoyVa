// Estimate from observed model latency, not task words or device names.
export function localContinuationEstimate({startedAt,now=Date.now(),lastModelMs,budgetMs=30000}){
 const remainingMs=budgetMs-(now-startedAt);
 if(!(lastModelMs>0))return {escalate:remainingMs<=0,remainingMs,estimatedNextMs:null};
 const estimatedNextMs=Math.max(4000,lastModelMs*1.5)+1000;
 return {escalate:remainingMs<estimatedNextMs,remainingMs,estimatedNextMs};
}
