import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_emails import spec_for, PROMPT, call_claude
from common import jl_read
cs = jl_read(sys.argv[1])[:2]
p = PROMPT.format(cases="\n\n".join(spec_for(c) for c in cs))
print(p[:2500])
print("=====")
print(call_claude(p, "sonnet")[:3000])
