"""Explicit additive rc1→rc2 upgrade. SQLite is backed up before any DDL.

PostgreSQL requires an operator-managed pg_dump and the existing `init` command;
this helper deliberately does not pretend to create a portable PostgreSQL backup.
"""
from pathlib import Path
from sqlalchemy import inspect
from .models import Meta
from .scout_models import SCOUT_TABLE_NAMES
from .backup import create_backup,verify_backup
from .errors import Problem


def upgrade_source_intake(product, backup_path):
    tables=set(inspect(product.db.engine).get_table_names())
    if 'product_meta' not in tables:
        raise Problem('不是重建版数据目录；新安装请运行setup，原系统请按迁移文档处理',409,'NOT_REBUILD_DATABASE')
    with product.db.tx(False) as s:
        version=s.get(Meta,'schema_version');scout=s.get(Meta,'scout_schema_version')
        if not version or version.value!='1' or (scout and scout.value!='1'):
            raise Problem('数据库版本不兼容；未做变更',409,'UPGRADE_VERSION')
        if scout and SCOUT_TABLE_NAMES.issubset(tables):
            return {'already_current':True,'source_intake_version':'1','data_modified':False}
    if not product.database_url.startswith('sqlite:///'):
        raise Problem('PostgreSQL请先停服务并用pg_dump备份，再执行init；本命令不代替数据库备份',409,'POSTGRES_BACKUP_REQUIRED')
    backup=create_backup(product.database_url,product.object_root,Path(backup_path))
    verify_backup(backup['backup'])
    product.initialize(allow_existing_upgrade=True)
    if not SCOUT_TABLE_NAMES.issubset(set(inspect(product.db.engine).get_table_names())):
        raise Problem('新增表未全部创建；备份已保留',503,'UPGRADE_INCOMPLETE')
    return {'source_intake_version':'1','backup':backup['backup'],'backup_verified':True,
            'already_current':False,'existing_rows_preserved':True,'sources_approved':0,'tasks_created':0}


ACTIONABLE_TABLE_NAMES={
    'product_opportunity_units','product_catalog_targets','product_target_actions',
    'product_target_feedback','product_target_notices'
}

def upgrade_actionable_catalog(product, backup_path):
    """Backup-first additive SG1 upgrade and rc2 publication backfill."""
    tables=set(inspect(product.db.engine).get_table_names())
    if 'product_meta' not in tables:
        raise Problem('不是重建版数据目录；新安装请运行setup',409,'NOT_REBUILD_DATABASE')
    with product.db.tx(False) as s:
        version=s.get(Meta,'schema_version')
        actionable=s.get(Meta,'actionable_schema_version')
        if not version or version.value!='1':
            raise Problem('数据库版本不兼容；未做变更',409,'UPGRADE_VERSION')
        if actionable and actionable.value=='2' and ACTIONABLE_TABLE_NAMES.issubset(tables):
            from .models import CatalogTarget,Publication
            from sqlalchemy import func,select
            current_publications=set(s.scalars(select(Publication.id).where(Publication.status.in_(['CURRENT','UPDATE_PENDING']))))
            projected_publications=set(s.scalars(select(CatalogTarget.publication_id).where(CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING']))))
            # create_all may have added SG1 tables/meta during an earlier additive
            # upgrade.  Only call the database SG1-complete when every current
            # publication already has an actionable projection.
            if current_publications.issubset(projected_publications):
                return {'already_current':True,'actionable_schema_version':'2',
                        'catalog_targets':s.scalar(select(func.count()).select_from(CatalogTarget)) or 0,
                        'data_modified':False}
    if not product.database_url.startswith('sqlite:///'):
        raise Problem('PostgreSQL请先停服务并用pg_dump备份，再执行init；本命令不代替数据库备份',409,'POSTGRES_BACKUP_REQUIRED')
    backup=create_backup(product.database_url,product.object_root,Path(backup_path))
    verify_backup(backup['backup'])
    product.initialize(allow_existing_upgrade=True)
    if not ACTIONABLE_TABLE_NAMES.issubset(set(inspect(product.db.engine).get_table_names())):
        raise Problem('行动目标新增表未全部创建；备份已保留',503,'UPGRADE_INCOMPLETE')
    from .catalog_projection import backfill_existing_catalog
    from .models import CatalogTarget
    from sqlalchemy import func,select
    with product.db.tx() as s:
        created=backfill_existing_catalog(s,product)
        meta=s.get(Meta,'actionable_schema_version')
        if not meta:s.add(Meta(key='actionable_schema_version',value='2'))
        else:meta.value='2'
        if created:product.db.tick(s)
    with product.db.tx(False) as s:
        total=s.scalar(select(func.count()).select_from(CatalogTarget)) or 0
    return {'actionable_schema_version':'2','backup':backup['backup'],'backup_verified':True,
            'already_current':False,'existing_rows_preserved':True,'catalog_targets_created':created,
            'catalog_targets':total}


def upgrade_time_semantics(product, backup_path):
    """Backup-first SG5.1 JSON projection refresh; no schema migration and no WMA rerun."""
    from sqlalchemy import select
    from .models import CatalogTarget
    current_states=('CURRENT','UPDATE_PENDING')
    with product.db.tx(False) as s:
        rows=list(s.scalars(select(CatalogTarget).where(CatalogTarget.status.in_(current_states))))
        missing=[r for r in rows if not isinstance(r.content,dict) or not isinstance(r.content.get('time_readiness'),dict) or not isinstance(r.content.get('milestones'),list)]
        if not missing:
            return {'already_current':True,'time_projection_version':'1','catalog_targets':len(rows),'data_modified':False}
    if not product.database_url.startswith('sqlite:///'):
        raise Problem('PostgreSQL请先停服务并用pg_dump备份，再执行时间语义刷新；本命令不代替数据库备份',409,'POSTGRES_BACKUP_REQUIRED')
    backup=create_backup(product.database_url,product.object_root,Path(backup_path))
    verify_backup(backup['backup'])
    from .milestones import refresh_current_targets
    with product.db.tx() as s:
        changed=refresh_current_targets(product,s)
        meta=s.get(Meta,'time_projection_version')
        if not meta:s.add(Meta(key='time_projection_version',value='1'))
        else:meta.value='1'
        if changed:product.db.tick(s)
    with product.db.tx(False) as s:
        total=len(list(s.scalars(select(CatalogTarget.id).where(CatalogTarget.status.in_(current_states)))))
    return {'already_current':False,'time_projection_version':'1','backup':backup['backup'],'backup_verified':True,
            'targets_refreshed':changed,'catalog_targets':total,'data_modified':bool(changed)}

ACTION_LOOP_TABLE_NAMES={'product_target_action_events','product_feedback_candidates'}

def upgrade_action_loop(product, backup_path):
    """Backup-first SG6 additive schema + migration of existing current action/feedback state."""
    from sqlalchemy import inspect, select, func
    from .models import (
        Meta, TargetAction, TargetActionEvent, TargetFeedback, FeedbackCandidate, CatalogTarget, Opportunity
    )
    tables=set(inspect(product.db.engine).get_table_names())
    if 'product_meta' not in tables:
        raise Problem('不是重建版数据目录；新安装请运行setup',409,'NOT_REBUILD_DATABASE')
    with product.db.tx(False) as s:
        version=s.get(Meta,'schema_version');loop=s.get(Meta,'action_loop_schema_version')
        if not version or version.value!='1':raise Problem('数据库版本不兼容；未做变更',409,'UPGRADE_VERSION')
        if loop and loop.value=='1' and ACTION_LOOP_TABLE_NAMES.issubset(tables):
            return {'already_current':True,'action_loop_schema_version':'1','data_modified':False,
                    'action_events':s.scalar(select(func.count()).select_from(TargetActionEvent)) or 0,
                    'feedback_candidates':s.scalar(select(func.count()).select_from(FeedbackCandidate)) or 0}
    if not product.database_url.startswith('sqlite:///'):
        raise Problem('PostgreSQL请先停服务并用pg_dump备份，再执行init；本命令不代替数据库备份',409,'POSTGRES_BACKUP_REQUIRED')
    backup=create_backup(product.database_url,product.object_root,Path(backup_path));verify_backup(backup['backup'])
    product.initialize(allow_existing_upgrade=True)
    if not ACTION_LOOP_TABLE_NAMES.issubset(set(inspect(product.db.engine).get_table_names())):
        raise Problem('SG6新增表未全部创建；备份已保留',503,'UPGRADE_INCOMPLETE')
    migrated_actions=0;migrated_feedback=0
    with product.db.tx() as s:
        if not s.scalar(select(func.count()).select_from(TargetActionEvent)):
            for action in s.scalars(select(TargetAction)):
                s.add(TargetActionEvent(account_id=action.account_id,target_public_id=action.target_public_id,
                    opportunity_id=action.opportunity_id,from_status=None,to_status=action.status,note=action.note,
                    event_type='MIGRATED_CURRENT_STATE',created_at=action.updated_at));migrated_actions+=1
        existing_feedback=set(s.scalars(select(FeedbackCandidate.feedback_id)))
        for fb in s.scalars(select(TargetFeedback)):
            if fb.id in existing_feedback:continue
            target=s.scalar(select(CatalogTarget).where(CatalogTarget.public_id==fb.target_public_id).order_by(CatalogTarget.created_at.desc()))
            action=s.scalar(select(TargetAction).where(TargetAction.account_id==fb.account_id,TargetAction.target_public_id==fb.target_public_id))
            data=fb.data if isinstance(fb.data,dict) else {}
            payload={'opportunity_type':(target.content or {}).get('type') if target else None,
                     'previously_known':data.get('previously_known'),'useful':data.get('useful'),
                     'action_reason':data.get('action_reason'),'outcome':data.get('outcome'),
                     'action_status':action.status if action else None,'comment_present':bool(data.get('comment')),
                     'source':'USER_FEEDBACK'}
            s.add(FeedbackCandidate(feedback_id=fb.id,target_public_id=fb.target_public_id,
                opportunity_id=fb.opportunity_id,candidate_kind='OUTCOME' if data.get('outcome') else 'SIGNAL',
                state='CANDIDATE',data=payload,created_at=fb.created_at));migrated_feedback+=1
        meta=s.get(Meta,'action_loop_schema_version')
        if not meta:s.add(Meta(key='action_loop_schema_version',value='1'))
        else:meta.value='1'
    return {'already_current':False,'action_loop_schema_version':'1','backup':backup['backup'],'backup_verified':True,
            'existing_rows_preserved':True,'migrated_action_events':migrated_actions,
            'migrated_feedback_candidates':migrated_feedback,'data_modified':True}


def upgrade_qualification_compiler(product, backup_path):
    """Backup-first SG6.2 refresh of rebuildable qualification compiler metadata.

    This does not create or approve facts/rules and does not alter WMA source
    artifacts.  It only annotates current CatalogTarget projections with a
    deterministic pre-evidence compiler summary used for diagnostics and
    migration/idempotence checks.
    """
    from sqlalchemy import select
    from .models import CatalogTarget
    from .qualification_compiler import summarize_content, COMPILER_PROJECTION_VERSION

    current_states=('CURRENT','UPDATE_PENDING')
    with product.db.tx(False) as s:
        rows=list(s.scalars(select(CatalogTarget).where(CatalogTarget.status.in_(current_states))))
        meta=s.get(Meta,'qualification_compiler_version')
        missing=[]
        for row in rows:
            body=row.content if isinstance(row.content,dict) else {}
            summary=body.get('qualification_compiler') if isinstance(body.get('qualification_compiler'),dict) else {}
            if summary.get('version')!=COMPILER_PROJECTION_VERSION:
                missing.append(row.id)
        if not missing and meta and meta.value==str(COMPILER_PROJECTION_VERSION):
            return {
                'already_current':True,'qualification_compiler_version':str(COMPILER_PROJECTION_VERSION),
                'catalog_targets':len(rows),'targets_refreshed':0,'data_modified':False,
            }

    if not product.database_url.startswith('sqlite:///'):
        raise Problem('PostgreSQL请先停服务并用pg_dump备份，再执行资格编译投影刷新；本命令不代替数据库备份',409,'POSTGRES_BACKUP_REQUIRED')
    backup=create_backup(product.database_url,product.object_root,Path(backup_path));verify_backup(backup['backup'])
    changed=0
    with product.db.tx() as s:
        rows=list(s.scalars(select(CatalogTarget).where(CatalogTarget.status.in_(current_states))))
        for row in rows:
            body=dict(row.content) if isinstance(row.content,dict) else {}
            summary=summarize_content(body)
            if body.get('qualification_compiler')!=summary:
                body['qualification_compiler']=summary
                row.content=body
                changed+=1
        meta=s.get(Meta,'qualification_compiler_version')
        if not meta:s.add(Meta(key='qualification_compiler_version',value=str(COMPILER_PROJECTION_VERSION)))
        else:meta.value=str(COMPILER_PROJECTION_VERSION)
        if changed:product.db.tick(s)
    return {
        'already_current':False,'qualification_compiler_version':str(COMPILER_PROJECTION_VERSION),
        'backup':backup['backup'],'backup_verified':True,'targets_refreshed':changed,
        'catalog_targets':len(rows),'data_modified':bool(changed),
    }

LAB_TABLE_NAMES={
    'product_lab_gold_cases','product_lab_pair_truths','product_lab_twins','product_lab_runs','product_lab_run_results',
    'product_lab_enrollments','product_lab_exposures',
}

def upgrade_opportunity_lab(product, backup_path):
    """Backup-first SG7 additive lab schema. Production facts and authority stay untouched."""
    from sqlalchemy import func, select
    from .models import LabEnrollment, LabGoldCase, LabRun, LabTwin
    tables=set(inspect(product.db.engine).get_table_names())
    if 'product_meta' not in tables:
        raise Problem('不是重建版数据目录；新安装请运行setup',409,'NOT_REBUILD_DATABASE')
    with product.db.tx(False) as s:
        version=s.get(Meta,'schema_version');lab=s.get(Meta,'opportunity_lab_schema_version')
        if not version or version.value!='1':raise Problem('数据库版本不兼容；未做变更',409,'UPGRADE_VERSION')
        if lab and lab.value=='2' and LAB_TABLE_NAMES.issubset(tables):
            return {'already_current':True,'opportunity_lab_schema_version':'2','data_modified':False,
                    'synthetic_twins':s.scalar(select(func.count()).select_from(LabTwin)) or 0,
                    'lab_cases':s.scalar(select(func.count()).select_from(LabGoldCase)) or 0,
                    'lab_runs':s.scalar(select(func.count()).select_from(LabRun)) or 0,
                    'enrollments':s.scalar(select(func.count()).select_from(LabEnrollment)) or 0}
    if not product.database_url.startswith('sqlite:///'):
        raise Problem('PostgreSQL请先停服务并用pg_dump备份，再执行init；本命令不代替数据库备份',409,'POSTGRES_BACKUP_REQUIRED')
    backup=create_backup(product.database_url,product.object_root,Path(backup_path));verify_backup(backup['backup'])
    product.initialize(allow_existing_upgrade=True)
    current=set(inspect(product.db.engine).get_table_names())
    if not LAB_TABLE_NAMES.issubset(current):
        raise Problem('SG7机会实验室新增表未全部创建；备份已保留',503,'UPGRADE_INCOMPLETE')
    with product.db.tx() as s:
        meta=s.get(Meta,'opportunity_lab_schema_version')
        if not meta:s.add(Meta(key='opportunity_lab_schema_version',value='2'))
        else:meta.value='2'
        # SG7.1 keeps V1 twins/pair truths/runs as historical evidence but removes
        # them from the active benchmark set. V2 twins are regenerated explicitly
        # from the deterministic SG7.1 generator, never by mutating V1 profiles.
        old_twins=list(s.scalars(select(LabTwin).where(LabTwin.version!=2,LabTwin.active.is_(True))))
        for twin in old_twins:twin.active=False
    return {'already_current':False,'opportunity_lab_schema_version':'2','backup':backup['backup'],'backup_verified':True,
            'existing_rows_preserved':True,'production_facts_modified':False,'wma_called':False,'data_modified':True,
            'historical_twins_deactivated':len(old_twins),'v2_twin_generation_required':bool(old_twins)}
