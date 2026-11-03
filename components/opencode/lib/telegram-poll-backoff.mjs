export function pollBackoffMs(failures,retryAfterMs=0){
 return Math.max(Math.min(300000,Math.max(0,Number(retryAfterMs)||0)),Math.min(60000,3000*2**Math.min(5,Math.max(0,failures-1))));
}
