"""Independently flatten the previously reviewed five CHIRRTL top type strings.
Only parses a small pinned review JSON; never reads or parses target FIRRTL.
"""
import json,re
from pathlib import Path
T=re.compile(r'\s*(UInt|SInt|Clock|Reset|flip|[A-Za-z_][A-Za-z_0-9]*|\d+|[{}<>\[\]:,])')
def parse_type(text):
    tokens=[];pos=0
    while pos<len(text):
        m=T.match(text,pos)
        if not m:raise ValueError('unparsed type text')
        tokens.append(m[1]);pos=m.end()
    at=0
    def take(expected=None):
        nonlocal at
        if at>=len(tokens):raise ValueError('unexpected type EOF')
        t=tokens[at];at+=1
        if expected is not None and t!=expected:raise ValueError('bad type token')
        return t
    def typ():
        if tokens[at]=='{':
            take('{');fields=[]
            while tokens[at]!='}':
                flipped=False
                if tokens[at]=='flip':take();flipped=True
                n=take();take(':');fields.append((n,flipped,typ()))
                if tokens[at]==',':take(',')
                elif tokens[at]!='}':raise ValueError('type separator')
            take('}');node=('bundle',fields)
        else:
            name=take()
            if name in ('UInt','SInt'):take('<');width=int(take());take('>')
            elif name in ('Clock','Reset'):width=1
            else:raise ValueError('unknown primitive')
            node=('ground',width,name=='SInt')
        while at<len(tokens) and tokens[at]=='[':
            take('[');n=int(take());take(']');node=('vector',n,node)
        return node
    node=typ()
    if at!=len(tokens):raise ValueError('trailing type')
    return node

def flatten(node,name,direction,out):
    if node[0]=='ground':
        if name in out:raise ValueError('flatten collision')
        out[name]=dict(direction=direction,width=node[1],signed=node[2])
    elif node[0]=='vector':
        for i in range(node[1]):flatten(node[2],name+'_'+str(i),direction,out)
    else:
        for n,flip,t in node[1]:flatten(t,name+'_'+n,('output' if direction=='input' else 'input') if flip else direction,out)

def derive(review):
    out={}
    for n,p in review['top_ports'].items():flatten(parse_type(p['type']),n,p['direction'],out)
    return out

