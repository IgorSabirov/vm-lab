function replay(){
 const assert=(p,m)=>{if(!p)throw Error(m)};
 const mul=(A,B)=>A.map(r=>B[0].map((_,j)=>r.reduce((s,x,k)=>s+x*B[k][j],0n)));
 const I=[[1n,0n],[0n,1n]],M=[[1n,1n],[1n,0n]],N=[[1n,-1n],[1n,0n]],tr=A=>A[0][0]+A[1][1];
 const mu=n=>{let s=1;for(let p=2;p*p<=n;p++){if(n%p===0){n/=p;s=-s;if(n%p===0)return 0;}}return n>1?-s:s};
 const ds=n=>Array.from({length:n},(_,i)=>i+1).filter(d=>n%d===0);
 let A=I,B=I;const a=[0n],b=[0n],p=[0n],rows=[];
 for(let n=1;n<=64;n++){
  A=mul(A,M);B=mul(B,N);a[n]=tr(A);b[n]=tr(B);
  assert(b[n]===[2n,1n,-1n,-2n,-1n,1n][n%6],"signed "+n);
  const q=ds(n).reduce((s,d)=>s+BigInt(mu(d))*a[n/d],0n);
  assert(q>=0n&&q%BigInt(n)===0n,"primitive "+n);p[n]=q/BigInt(n);
  assert(ds(n).reduce((s,d)=>s+BigInt(d)*p[d],0n)===a[n],"inversion "+n);
  rows.push({n,periodic_words:String(a[n]),signed_sum:String(b[n]),primitive_orbits:String(p[n])});
 }
 let brute=0;
 for(let n=1;n<=16;n++){
  let ca=0n,cb=0n,oa=0n,ob=0n;
  for(let w=0;w<(1<<n);w++){brute++;if(w&(w<<1))continue;let k=0;for(let v=w;v;v>>=1)k+=v&1;const s=k%2?-1n:1n;oa++;ob+=s;if((w&1)&&(w&(1<<(n-1))))continue;ca++;cb+=s;}
  assert(ca===a[n]&&cb===b[n],"cyclic brute "+n);
  let x=1n,y=1n,z=1n,t=0n;for(let i=1;i<=n;i++){[x,y]=[x+y,x];[z,t]=[z+t,-z];}
  assert(x===oa&&z+t===ob,"open brute "+n);
 }
 const add=([a,b],[c,d])=>[a+c,b+d],mm=([a,b],[c,d])=>[a*c+b*d,a*d+b*c+b*d],eq=(a,b)=>a[0]===b[0]&&a[1]===b[1];
 const one=[1n,0n],minus=[-1n,0n],v0=[-1n,1n],v1=[2n,-1n],lambda=[-2n,1n];assert(eq(add(v0,v1),one),"row norm");
 let v=[one,minus],power=one;for(let n=0;n<=64;n++){assert(eq(v[0],power)&&eq(v[1],mm(minus,power)),"Parry "+n);v=[add(mm(v[0],v0),v[1]),mm(v[0],v1)];power=mm(power,lambda);}
 const phi=(1+Math.sqrt(5))/2;
 return {schema:"r141-ym-mobius-transfer-checks-v1",scope:"finite exact model; no physical YM/BBN runs; no RH proof",cyclic_trace_lengths:64,mobius_inversion_lengths:64,parry_difference_powers:65,brute_word_candidates:brute,brute_lengths:16,constants:{phi,entropy:Math.log(phi),tv_ratio:phi**-2,xi_steps:1/(2*Math.log(phi)),xi_inverse:2*Math.log(phi),two_step_gap_times_ell:4*Math.log(phi),signed_ratio_bound_rate:Math.log(phi)},rows};
}
console.log(JSON.stringify(replay(),null,2));
