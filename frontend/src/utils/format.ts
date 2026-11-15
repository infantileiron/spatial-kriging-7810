export const fixed=(v:unknown,n=3)=>{const x=Number(v||0);return (Math.abs(x)<1e-12?0:x).toFixed(n)};export const scientific=(v:unknown)=>Number(v||0).toExponential(2);
