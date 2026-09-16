from __future__ import annotations

import html
import re
import sqlite3
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from matching.tv_matcher import TVMatcher

PRAGUE = ZoneInfo("Europe/Prague")
UTC = timezone.utc

DAY_NAMES = ("Pondělí", "Úterý", "Středa", "Čtvrtek", "Pátek", "Sobota", "Neděle")
MONTH_NAMES = ("", "ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září", "října", "listopadu", "prosince")
COUNTRIES = {"AT":"Rakousko","AUT":"Rakousko","AUSTRIA":"Rakousko","BE":"Belgie","BEL":"Belgie","BELGIUM":"Belgie","CH":"Švýcarsko","CHE":"Švýcarsko","SWITZERLAND":"Švýcarsko","CZ":"Česko","CZE":"Česko","CZECHIA":"Česko","CZECH REPUBLIC":"Česko","DE":"Německo","DEU":"Německo","GERMANY":"Německo","DK":"Dánsko","DN":"Dánsko","DNK":"Dánsko","DENMARK":"Dánsko","EE":"Estonsko","EST":"Estonsko","ESTONIA":"Estonsko","FI":"Finsko","FIN":"Finsko","FINLAND":"Finsko","FR":"Francie","FRA":"Francie","FRANCE":"Francie","HU":"Maďarsko","HUN":"Maďarsko","HUNGARY":"Maďarsko","IT":"Itálie","ITA":"Itálie","ITALY":"Itálie","LV":"Lotyšsko","LVA":"Lotyšsko","LATVIA":"Lotyšsko","NO":"Norsko","NOR":"Norsko","NORWAY":"Norsko","PL":"Polsko","POL":"Polsko","POLAND":"Polsko","RO":"Rumunsko","ROU":"Rumunsko","ROMANIA":"Rumunsko","SE":"Švédsko","SWE":"Švédsko","SWEDEN":"Švédsko","SI":"Slovinsko","SVN":"Slovinsko","SLOVENIA":"Slovinsko","SK":"Slovensko","SVK":"Slovensko","SLOVAKIA":"Slovensko","US":"USA","USA":"USA","UNITED STATES":"USA","CA":"Kanada","CAN":"Kanada","CANADA":"Kanada"}
HOCKEY_TEAM_COUNTRIES = {"gks tychy":"Polsko","rogle bk":"Švédsko","rogle angelholm":"Švédsko","saipa lappeenranta":"Finsko","kookoo kouvola":"Finsko","bordeaux boxers":"Francie","vaxjo lakers":"Švédsko"}
CHANNEL_ALIASES = {"ct sport":"ČT sport","ct sport hd":"ČT sport","ct2":"ČT2","nova sport 1 hd":"Nova Sport 1","nova sport 2 hd":"Nova Sport 2","oneplay sport 1 hd":"Oneplay Sport 1","oneplay sport 2 hd":"Oneplay Sport 2","oneplay sport 3 hd":"Oneplay Sport 3","oneplay sport 4 hd":"Oneplay Sport 4"}
REPLAY_TERMS = ("archiv", "zaznam", "repriza", "opakovani", "ze zaznamu")
SPORT_PRIORITY = {"hockey":0,"biathlon":1,"athletics":2}

@dataclass(frozen=True)
class Broadcast:
    event_id:int; sport:str; competition:str; event_name:str; location:str|None; country:str|None; source_url:str; tv_start:datetime; tv_end:datetime|None; channel:str; distribution:str; tv_title:str

@dataclass(frozen=True)
class DigestItem:
    key:str; sport:str; competition:str; title:str; location:str|None; country:str|None; start:datetime; broadcasts:tuple[Broadcast,...]

def _norm(value):
    if not value: return ""
    value=unicodedata.normalize("NFKD",value); value="".join(ch for ch in value if not unicodedata.combining(ch)); value=value.casefold().replace("–","-").replace("—","-"); return " ".join(re.sub(r"[^a-z0-9]+"," ",value).split())
def _parse_dt(value):
    if not value:return None
    dt=datetime.fromisoformat(value.replace("Z","+00:00")); return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)
def _sport_name(value):
    n=_norm(value); return "hockey" if "hockey" in n or "hokej" in n else "biathlon" if "biathlon" in n or "biatlon" in n else "athletics"
def _country_cs(value): return None if not value else COUNTRIES.get(value.strip().upper(),value.strip().title())
def _location_cs(value):
    if not value:return None
    known={"BRUSSELS":"Brusel","BUDAPEST":"Budapešť","HOCHFILZEN":"Hochfilzen","KONTIOLAHTI":"Kontiolahti","LE GRAND BORNAND":"Le Grand-Bornand","MUNICH":"Mnichov","MÜNCHEN":"Mnichov","NOVE MESTO":"Nové Město","NOVÉ MĚSTO":"Nové Město","OBERHOF":"Oberhof","RUHPOLDING":"Ruhpolding","SJUSJOEN":"Sjusjøen","SJUSJØEN":"Sjusjøen","IDRE FJAELL":"Idre Fjäll","IDRE FJÄLL":"Idre Fjäll"}; return known.get(value.strip().upper(),value.strip().title())
def _channel_name(value):
    normalized=_norm(value)
    if normalized in CHANNEL_ALIASES:return CHANNEL_ALIASES[normalized]
    normalized=re.sub(r"\s+hd$","",normalized).strip(); return CHANNEL_ALIASES.get(normalized,value.strip().removesuffix(" HD"))
def _is_replay(*parts):
    text=_norm(" ".join(part or "" for part in parts)); return any(term in text for term in REPLAY_TERMS)
def _event_live_end(event):
    start=_parse_dt(event["start_datetime"]); explicit=_parse_dt(event["end_datetime"])
    if explicit:return explicit
    return start+{"hockey":timedelta(hours=3,minutes=30),"biathlon":timedelta(hours=2),"athletics":timedelta(hours=4)}[_sport_name(event["sport"])]
def _is_live_timing(event,tv):
    event_start=_parse_dt(event["start_datetime"]); tv_start=_parse_dt(tv["start_datetime"]); tv_end=_parse_dt(tv["end_datetime"])
    if event_start is None or tv_start is None:return False
    return tv_start<=_event_live_end(event) and (tv_end or tv_start+timedelta(hours=3))>=event_start-timedelta(hours=1)
def _competition_cs(event):
    value=event.competition.strip(); n=_norm(value)
    if event.sport=="biathlon" and "biathlonworld.com" in event.source_url:
        u=event.source_url.upper()
        if "SWRLCP" in u:return "Světový pohár"
        if "SWRLCH" in u:return "Mistrovství světa"
    return {"liga mistru":"Liga mistrů","tipsport extraliga":"Extraliga","wanda diamond league":"Diamond League","diamond league":"Diamond League","world athletics ultimate championship":"World Athletics Ultimate Championship","international biathlon union":"Biatlon"}.get(n,value)
def _biathlon_name_cs(value):
    text=value.upper().strip(); gender="žen" if text.startswith("WOMEN") else "mužů" if text.startswith("MEN") else ""; m=re.search(r"(\d+(?:\.\d+)?)\s*KM",text); distance=m.group(1).replace(".5",",5")+" km" if m else ""
    if "SUPER SPRINT" in text: discipline="Super sprint"
    elif "SPRINT" in text: discipline="Sprint"
    elif "PURSUIT" in text: discipline="Stíhací závod"
    elif "INDIVIDUAL" in text: discipline="Vytrvalostní závod"
    elif "MASS START" in text: discipline="Hromadný start"
    elif "SINGLE MIXED RELAY" in text:return "Smíšená štafeta dvojic"
    elif "MIXED RELAY" in text:return "Smíšená štafeta"
    elif "RELAY" in text:discipline="Štafeta"
    else:return value.title()
    return " ".join(x for x in (discipline,gender,distance if "RELAY" not in text else "") if x)
def _hockey_title(event):
    title=event.event_name.replace(" - "," – ")
    if _norm(event.competition)!="liga mistru":return title
    teams=re.split(r"\s+[–-]\s+",title)
    if len(teams)!=2:return title
    for i,team in enumerate(teams):
        if "dynamo pardubice" not in _norm(team) and _norm(team) in HOCKEY_TEAM_COUNTRIES:teams[i]=f"{team} ({HOCKEY_TEAM_COUNTRIES[_norm(team)]})"
    return " – ".join(teams)
def _athletics_title(event):
    location=_location_cs(event.location); country=_country_cs(event.country); return f"{location} ({country})" if location and country else location or event.event_name
def _format_date(value):return f"{DAY_NAMES[value.weekday()]} {value.day}. {MONTH_NAMES[value.month]}"
def _group_key(b,local_day):return f"athletics|{_norm(b.competition)}|{_norm(b.location)}|{local_day.isoformat()}" if b.sport=="athletics" else f"event|{b.event_id}"

def _dedupe_broadcasts(rows):
    """Keep one live entry per normalized distribution/channel for an event.

    EPG providers often split one live transmission into adjacent studio/game blocks.
    For delivery purposes that is still one channel. Keep its earliest live block;
    distinct channels and TV/online distributions remain separate.
    """
    best={}
    for row in sorted(rows,key=lambda x:x.tv_start):
        normalized=Broadcast(row.event_id,row.sport,row.competition,row.event_name,row.location,row.country,row.source_url,row.tv_start,row.tv_end,_channel_name(row.channel),row.distribution,row.tv_title)
        best.setdefault((normalized.distribution,normalized.channel),normalized)
    return tuple(sorted(best.values(),key=lambda x:(x.tv_start,x.distribution!="tv",x.channel)))

def collect_today_items(db_path="data/sports_events.db",*,now=None):
    now_local=(now or datetime.now(PRAGUE)).astimezone(PRAGUE); today=now_local.date(); matcher=TVMatcher(db_path); details=matcher.candidate_details(c for c in matcher.find_candidates(min_score=70) if c.status=="match"); grouped=defaultdict(list)
    for _,event,tv in details:
        tv_start=_parse_dt(tv["start_datetime"])
        if tv_start is None or tv_start.astimezone(PRAGUE).date()!=today:continue
        if _is_replay(tv["title"] or "",tv["description"] or "") or not _is_live_timing(event,tv):continue
        b=Broadcast(int(event["id"]),_sport_name(event["sport"]),event["competition"] or "",event["name"] or "",event["location"],event["country"],event["source_url"] or "",tv_start.astimezone(PRAGUE),_parse_dt(tv["end_datetime"]),tv["channel"] or "",(tv["distribution"] or "tv").lower(),tv["title"] or ""); grouped[_group_key(b,today)].append(b)
    items=[]
    for key,rows in grouped.items():
        broadcasts=_dedupe_broadcasts(rows)
        if not broadcasts:continue
        first=min(rows,key=lambda x:x.tv_start)
        if first.sport=="hockey":title,location,country=_hockey_title(first),None,None
        elif first.sport=="biathlon":title,location,country=_biathlon_name_cs(first.event_name),_location_cs(first.location),_country_cs(first.country)
        else:title,location,country=_athletics_title(first),None,None
        items.append(DigestItem(key,first.sport,_competition_cs(first),title,location,country,min(b.tv_start for b in broadcasts),broadcasts))
    return items

def _media_signature(item):return tuple((b.distribution,_channel_name(b.channel),b.tv_start.strftime("%H:%M")) for b in item.broadcasts)
def _media_lines(broadcasts,main_start):
    grouped=defaultdict(list)
    for b in broadcasts:
        kind="online" if b.distribution=="online" else "tv"; channel=_channel_name(b.channel); suffix="" if b.tv_start==main_start else f" od {b.tv_start:%H:%M}"; grouped[kind].append(f"{html.escape(channel)}{suffix}")
    lines=[]
    if grouped["tv"]:lines.append(" • ".join(f"📺 {entry}" for entry in grouped["tv"]))
    if grouped["online"]:lines.append(" • ".join(f"💻 {entry}" for entry in grouped["online"]))
    return lines

def _format_hockey(items):
    lines=["🏒 <b>HOKEJ</b>"]; by_comp=defaultdict(list)
    for item in sorted(items,key=lambda x:x.start):by_comp[item.competition].append(item)
    for index,competition in enumerate(sorted(by_comp,key=lambda c:min(i.start for i in by_comp[c]))):
        if index:lines.append("")
        if competition:lines.append(f"🏆 {html.escape(competition)}")
        for item_index,item in enumerate(by_comp[competition]):
            if item_index:lines.append("")
            lines.append(f"<b>{item.start:%H:%M}</b>  {html.escape(item.title)}"); lines.extend(_media_lines(item.broadcasts,item.start))
    return lines

def _format_biathlon(items):
    lines=["🎯 <b>BIATLON</b>"]; groups=defaultdict(list)
    for item in items:groups[(item.competition,item.location,item.country)].append(item)
    for group_index,group in enumerate(sorted(groups.values(),key=lambda g:min(i.start for i in g))):
        group.sort(key=lambda x:x.start)
        if group_index:lines.append("")
        first=group[0]
        if first.competition:lines.append(f"🏆 {html.escape(first.competition)}")
        if first.location:lines.append(html.escape(first.location+(f" ({first.country})" if first.country else "")))
        shared_media=len({_media_signature(item) for item in group})==1
        for idx,item in enumerate(group):
            lines.append(f"<b>{item.start:%H:%M}</b>  {html.escape(item.title)}")
            if not shared_media:lines.extend(_media_lines(item.broadcasts,item.start))
            if idx!=len(group)-1 and not shared_media:lines.append("")
        if shared_media:lines.extend(_media_lines(first.broadcasts,first.start))
    return lines

def _format_athletics(items):
    lines=["🏃 <b>ATLETIKA</b>"]; current_comp=None
    for item in sorted(items,key=lambda x:x.start):
        if item.competition!=current_comp:
            if current_comp is not None:lines.append("")
            if item.competition:lines.append(f"🏆 {html.escape(item.competition)}")
            current_comp=item.competition
        elif current_comp is not None:lines.append("")
        lines.append(f"<b>{item.start:%H:%M}</b>  {html.escape(item.title)}"); lines.extend(_media_lines(item.broadcasts,item.start))
    return lines

def format_digest(items,*,day):
    if not items:return None
    by_sport=defaultdict(list)
    for item in items:by_sport[item.sport].append(item)
    sports=sorted(by_sport,key=lambda sport:(min(i.start for i in by_sport[sport]),SPORT_PRIORITY.get(sport,99))); lines=[html.escape(_format_date(day))]; formatters={"hockey":_format_hockey,"biathlon":_format_biathlon,"athletics":_format_athletics}
    for sport in sports:lines.append(""); lines.extend(formatters[sport](by_sport[sport]))
    return "\n".join(lines).strip()
def build_today_digest(db_path="data/sports_events.db",*,now=None):
    now_local=(now or datetime.now(PRAGUE)).astimezone(PRAGUE); return format_digest(collect_today_items(db_path,now=now_local),day=now_local.date())
