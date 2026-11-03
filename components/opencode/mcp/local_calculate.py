import ast,json,sys,re
from fractions import Fraction
from decimal import Decimal,localcontext,ROUND_HALF_UP
req=json.load(sys.stdin);expr=req['expression']
if len(expr)>240:raise ValueError('Expression too long')
tree=ast.parse(expr,mode='eval')
if sum(1 for _ in ast.walk(tree))>100:raise ValueError('Expression too complex')
def calc(n):
 if isinstance(n,ast.Constant) and type(n.value) in [int,float]:
  raw=ast.get_source_segment(expr,n)
  if len(raw)>64:raise ValueError('Number too long')
  x=Fraction(raw)
  if req.get('allowedNumbers') is not None and abs(x) not in {abs(Fraction(str(v))) for v in req['allowedNumbers']}:raise ValueError('Number not grounded in current request')
  return x
 if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.USub,ast.UAdd)):
  x=calc(n.operand);return -x if isinstance(n.op,ast.USub) else x
 if isinstance(n,ast.BinOp):
  a,b=calc(n.left),calc(n.right)
  if isinstance(n.op,ast.Add):x=a+b
  elif isinstance(n.op,ast.Sub):x=a-b
  elif isinstance(n.op,ast.Mult):x=a*b
  elif isinstance(n.op,ast.Div):x=a/b
  elif isinstance(n.op,ast.FloorDiv):x=Fraction(a//b)
  elif isinstance(n.op,ast.Mod):x=a%b
  elif isinstance(n.op,ast.Pow) and b.denominator==1 and abs(b)<=12:x=a**int(b)
  else:raise ValueError('Unsupported operator')
  if x.numerator.bit_length()>4096 or x.denominator.bit_length()>4096:raise ValueError('Result too large')
  return x
 raise ValueError('Only arithmetic literals and operators are permitted')
x=calc(tree.body)
if req.get('fraction'):answer=str(x)
else:
 with localcontext() as c:
  c.prec=40;d=Decimal(x.numerator)/Decimal(x.denominator)
  places=req.get('places')
  if places is not None:
   if type(places) is not int or not 0<=places<=12:raise ValueError('Invalid precision')
   answer=format(d.quantize(Decimal(1).scaleb(-places),rounding=ROUND_HALF_UP),'f')
  else:answer=format(d,'f').rstrip('0').rstrip('.') if '.' in format(d,'f') else str(d)
print(json.dumps({'expression':expr,'answer':answer}))
