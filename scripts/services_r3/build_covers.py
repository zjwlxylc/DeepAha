"""Deterministic brand composition; existing master logo is reused unchanged.
Fonts come from the build host only and are never distributed with the product.
"""
from pathlib import Path
import math, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'web/public/product/share';OUT.mkdir(parents=True,exist_ok=True)
BOLD='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
REG='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
S=2

def font(size,bold=False):return ImageFont.truetype(BOLD if bold else REG,int(size*S))
def logo_tile(size):
    tile=Image.open(ROOT/'web/public/product/brand-logo.png').convert('RGBA').resize((size*S,size*S),Image.Resampling.LANCZOS)
    # Match the existing site's rounded icon presentation; source logo bytes stay unchanged.
    mask=Image.new('L',tile.size,0);ImageDraw.Draw(mask).rounded_rectangle((0,0,size*S-1,size*S-1),radius=int(size*.23*S),fill=255)
    tile.putalpha(mask);return tile

def compose(w,h,square=False):
    W,H=w*S,h*S
    img=Image.new('RGB',(W,H));pix=img.load()
    for y in range(H):
        for x in range(W):
            k=x/W;v=y/H
            if square:rgb=(int(4+6*k),int(26+24*k+6*v),int(77+73*k+15*v))
            else:
                t=max(0,min(1,(k-.42)/.58));rgb=(int(247-229*t),int(250-186*t),int(254-100*t))
            pix[x,y]=rgb
    d=ImageDraw.Draw(img)
    cx,cy=(w*.64,h*.63) if square else (w*.81,h*.54)
    layer=Image.new('RGBA',(W,H));ld=ImageDraw.Draw(layer)
    rng=random.Random(137)
    for r in (72,120,175,230,310):
        box=[int((cx-r)*S),int((cy-r*.63)*S),int((cx+r)*S),int((cy+r*.63)*S)]
        ld.ellipse(box,outline=(157,203,255,60),width=S)
    for i in range(72):
        x=rng.uniform(w*.4,w*1.04);y=rng.uniform(h*.04,h*.94)
        a=rng.randrange(45,155);r=rng.choice([1,1,1.5,2.2])
        ld.ellipse(((x-r)*S,(y-r)*S,(x+r)*S,(y+r)*S),fill=(218,237,255,a))
    path=[]
    for i in range(100):
        t=i/99;x=cx-150+310*t;y=cy+150-260*t+25*math.sin(t*math.pi*2)
        path.append((int(x*S),int(y*S)))
    ld.line(path,fill=(64,170,255,180),width=5*S)
    for t in (.18,.57,.91):
        x,y=path[int(t*99)]
        glow=Image.new('RGBA',(W,H));gd=ImageDraw.Draw(glow);r=23*S
        gd.ellipse((x-r,y-r,x+r,y+r),fill=(255,132,20,155));glow=glow.filter(ImageFilter.GaussianBlur(13*S));layer=Image.alpha_composite(layer,glow);ld=ImageDraw.Draw(layer)
        r=5*S;ld.ellipse((x-r,y-r,x+r,y+r),fill=(255,171,68,255))
        if t==.91:
            ld.polygon([(x,y-20*S),(x+4*S,y-4*S),(x+20*S,y),(x+4*S,y+4*S),(x,y+20*S),(x-4*S,y+4*S),(x-20*S,y),(x-4*S,y-4*S)],fill=(255,197,111,255))
    img=Image.alpha_composite(img.convert('RGBA'),layer);d=ImageDraw.Draw(img)
    if square:
        logo=logo_tile(136)
        img.alpha_composite(logo,(42*S,42*S));d=ImageDraw.Draw(img)
        d.text((42*S,219*S),'机会星图',font=font(67,True),fill='#FFFFFF')
        d.text((46*S,324*S),'找到真正属于你的',font=font(24),fill='#DCEBFF')
        d.text((46*S,363*S),'那一个机会。',font=font(30,True),fill='#FFAA4D')
        d.text((46*S,512*S),'DeepAha',font=font(28,True),fill='#FFFFFF')
    else:
        logo=logo_tile(62)
        img.alpha_composite(logo,(55*S,44*S));d=ImageDraw.Draw(img)
        d.text((133*S,49*S),'DeepAha',font=font(28,True),fill='#0B2670')
        d.text((135*S,85*S),'机会星图',font=font(15),fill='#36577E')
        d.text((55*S,184*S),'海量机会，',font=font(57,True),fill='#0B2670')
        d.text((55*S,266*S),'找到属于你的。',font=font(57,True),fill='#0B44B3')
        d.rounded_rectangle((57*S,362*S,129*S,369*S),radius=3*S,fill='#F86F09')
        d.text((57*S,408*S),'官方机会  ·  个人关注  ·  持续跟踪',font=font(21),fill='#45607C')
        d.text((57*S,526*S),'GO DEEP. FIND YOURS.',font=font(17,True),fill='#0B44B3')
        d.text((57*S,561*S),'deepaha.com',font=font(14),fill='#58718D')
    return img.convert('RGB').resize((w,h),Image.Resampling.LANCZOS)

if __name__=='__main__':
    for name,w,h,square in [('default-wide.jpg',1200,630,False),('default-square.jpg',600,600,True)]:
        compose(w,h,square).save(OUT/name,quality=93,optimize=True)
        print(name,(OUT/name).stat().st_size)
