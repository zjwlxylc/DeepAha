/** Commit pagination only after success, ignore older responses after a new search. */
export class SourcePages{
 constructor(){this.query='';this.offset=0;this.rows=[];this.generation=0;}
 async load(query,append,fetcher){
  const generation=++this.generation,extend=append&&query===this.query,offset=extend?this.offset+30:0;
  const result=await fetcher({q:query,offset,limit:30});
  if(generation!==this.generation)return null;
  this.query=query;this.offset=offset;this.rows=extend?[...this.rows,...result.items]:result.items;
  return {...result,items:this.rows,loaded:Math.min(offset+result.items.length,result.total)};
 }
}
