/* Linux ownership/JSON bridge. Upstream rule and vehicle sources stay unchanged.
 * Each handle is single-owner; callers must not use or close it concurrently. */
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "cJSON.h"
#include "tr_parse.h"
#include "tr_eval.h"
#include "vp_engine.h"
#include "app_obd_dsp/signal_store.h"

void sg_free(void *p) { free(p); }
static char *emit(cJSON *j) {
    if (!j) return NULL;
    char *s = cJSON_PrintUnformatted(j); cJSON_Delete(j); return s;
}
static void *allocate(void *ctx, size_t n) { (void)ctx; return calloc(1,n); }
static void release(void *ctx, void *p) { (void)ctx; free(p); }
static const vp_allocator_t allocator = {allocate, release, NULL};

typedef struct { tr_program_t *p; cJSON *keys; tr_diag_t diag; } rules_t;
static int resolve(const char *key, void *ctx) {
    rules_t *r=ctx; const cJSON *item; int i=0;
    cJSON_ArrayForEach(item,r->keys) {
        if (cJSON_IsString(item) && strcmp(item->valuestring,key)==0) return i;
        i++;
    }
    return -1;
}
void *sg_rules_open(const char *json, size_t len, const char *keys) {
    if (!json || len>262144 || !keys) return NULL;
    rules_t *r=calloc(1,sizeof(*r)); if (!r) return NULL;
    r->keys=cJSON_Parse(keys);
    if (!cJSON_IsArray(r->keys) || cJSON_GetArraySize(r->keys)>64) goto fail;
    tr_compile_cfg_t cfg={0}; cfg.resolve_source=resolve; cfg.resolve_ctx=r;
    if (tr_compile_json(json,len,&cfg,&r->p,&r->diag)!=TR_OK) goto fail;
    return r;
fail:
    cJSON_Delete(r->keys); free(r); return NULL;
}
void sg_rules_close(void *handle) {
    rules_t *r=handle; if (!r) return;
    tr_program_free(r->p); cJSON_Delete(r->keys); free(r);
}
char *sg_rules_report(void *handle) {
    rules_t *r=handle; if (!r) return NULL;
    cJSON *j=cJSON_CreateObject();
    cJSON_AddNumberToObject(j,"rules",r->p->n_rules);
    cJSON_AddNumberToObject(j,"targets",r->p->n_targets);
    cJSON_AddNumberToObject(j,"rules_dropped",r->diag.rules_dropped);
    cJSON_AddNumberToObject(j,"conditions_dropped",r->diag.conds_dropped);
    cJSON_AddNumberToObject(j,"actions_dropped",r->diag.actions_dropped);
    cJSON_AddNumberToObject(j,"unknown_sources",r->diag.unknown_sources);
    cJSON_AddNumberToObject(j,"unknown_targets",r->diag.unknown_targets);
    cJSON_AddNumberToObject(j,"bad_values",r->diag.bad_values);
    return emit(j);
}
void sg_rules_reset(void *handle) { rules_t *r=handle; if(r) tr_reset(r->p); }
char *sg_rules_tick(void *handle, const double *values, uint64_t invalid,
                    uint64_t changed, double ms) {
    rules_t *r=handle; if(!r || !isfinite(ms) || ms<0) return NULL;
    tr_inputs_t in={0}; in.values=values; in.n_values=(uint16_t)cJSON_GetArraySize(r->keys);
    in.invalid_mask=invalid; in.changed_mask=changed; in.elapsed_ms=ms;
    const tr_result_t *result=tr_eval(r->p,&in);
    cJSON *j=cJSON_CreateObject(), *active=cJSON_AddArrayToObject(j,"activeRules");
    cJSON *overrides=cJSON_AddObjectToObject(j,"overrides");
    for(unsigned i=0;i<result->n_active;i++)
        cJSON_AddItemToArray(active,cJSON_CreateString(r->p->rules[result->active[i]].id));
    for(unsigned i=0;i<result->n_targets;i++) {
        const tr_override_t *o=&result->ovr[i]; if(!o->touched) continue;
        cJSON *v=cJSON_AddObjectToObject(overrides,r->p->targets[i].id);
        if(o->props&TR_PROP_COLOR) cJSON_AddStringToObject(v,"color",o->color_str);
        if(o->props&TR_PROP_TINT) cJSON_AddStringToObject(v,"tintColor",o->color_str);
        if(o->props&TR_PROP_TEXT) cJSON_AddStringToObject(v,"text",o->text);
        if(o->props&TR_PROP_ASSET) cJSON_AddStringToObject(v,"assetName",o->asset);
        if(o->props&TR_PROP_VISIBLE) cJSON_AddBoolToObject(v,"visible",o->visible);
        if(o->animated_color) cJSON_AddNumberToObject(v,"animationProgress",o->animation_progress);
    }
    return emit(j);
}

typedef struct {
    vp_profile_t *p; vp_engine_t *e;
    uint32_t now,stamp[SIG_SLOT_COUNT]; int32_t val[SIG_SLOT_COUNT];
    unsigned char valid[SIG_SLOT_COUNT];
    char keys[SIG_SLOT_COUNT][32];
    uint32_t stale[SIG_SLOT_COUNT]; int veh_count;
    char command[24]; int pending,reconnect;
} vehicle_t;
static uint32_t now_ms(void *ctx) { return ((vehicle_t*)ctx)->now; }
static bool send_cmd(void *ctx,const char *cmd) {
    vehicle_t *v=ctx;
    if(v->pending || strlen(cmd)>=sizeof(v->command)) return false;
    strcpy(v->command,cmd); v->pending=1; return true;
}
static void write_signal(void *ctx,int slot,int32_t value) {
    vehicle_t *v=ctx; if(slot<0 || slot>=SIG_SLOT_COUNT) return;
    v->val[slot]=value; v->stamp[slot]=v->now; v->valid[slot]=1;
}
static void invalidate(void *ctx,int slot) {
    vehicle_t *v=ctx; if(slot>=0 && slot<SIG_SLOT_COUNT) v->valid[slot]=0;
}
static void speed(void *ctx,uint8_t kmh) { write_signal(ctx,SIG_OBD_SPEED,kmh); }
static void link_state(void *ctx,uint8_t state) {
    vehicle_t *v=ctx; write_signal(ctx,SIG_SYS_OBD_LINK,state);
    if(state!=SIG_LINK_DATA) for(int i=0;i<SIG_SLOT_COUNT;i++)
        if(i<SIG_OBD_COUNT || i>=SIG_VEH_BASE) v->valid[i]=0;
}
static void clear_veh(void *ctx) {
    vehicle_t *v=ctx; v->veh_count=0;
    for(int i=SIG_VEH_BASE;i<SIG_SLOT_COUNT;i++) {v->keys[i][0]=0;v->valid[i]=0;}
}
static int register_veh(void *ctx,const char *key,int32_t lo,int32_t hi,uint32_t stale) {
    (void)lo;(void)hi; vehicle_t *v=ctx;
    for(int i=SIG_VEH_BASE;i<SIG_VEH_BASE+v->veh_count;i++)
        if(!strcmp(v->keys[i],key)) return i;
    if(v->veh_count>=SIG_VEH_MAX || strlen(key)>31) return SIG_SLOT_NONE;
    int slot=SIG_VEH_BASE+v->veh_count++; strcpy(v->keys[slot],key);v->stale[slot]=stale;return slot;
}
static void reconnect(void *ctx) { ((vehicle_t*)ctx)->reconnect=1; }

void sg_vehicle_close(void *handle) {
    vehicle_t *v=handle; if(!v) return;
    vp_engine_destroy(v->e); vp_profile_free(v->p,&allocator); free(v);
}
void *sg_vehicle_open(const char *text,size_t len,char **report) {
    if(report) *report=NULL;
    if(!text || len>VP_MAX_JSON_BYTES) return NULL;
    vehicle_t *v=calloc(1,sizeof(*v));if(!v)return NULL;
    vp_issue_t storage[64];vp_issues_t issues;vp_issues_init(&issues,storage,64);
    vp_compile_err_t err=vp_compile_json(text,len,vp_validate_default_cfg(),&allocator,&v->p,&issues);
    cJSON *j=cJSON_CreateObject(),*items=cJSON_AddArrayToObject(j,"issues");
    cJSON_AddBoolToObject(j,"ok",err==VP_COMPILE_OK);
    cJSON_AddNumberToObject(j,"errors",issues.n_errors);
    cJSON_AddNumberToObject(j,"warnings",issues.n_warnings);
    for(size_t i=0;i<issues.count;i++) {
        cJSON *item=cJSON_CreateObject();cJSON_AddItemToArray(items,item);
        cJSON_AddStringToObject(item,"code",storage[i].code);
        cJSON_AddStringToObject(item,"path",storage[i].path);
        cJSON_AddStringToObject(item,"msg",storage[i].msg);
    }
    if(err==VP_COMPILE_OK) {
        cJSON_AddStringToObject(j,"id",v->p->id);cJSON_AddStringToObject(j,"name",v->p->name);
        cJSON_AddNumberToObject(j,"rev",v->p->rev);
        cJSON_AddNumberToObject(j,"signals",v->p->n_sig);
        cJSON_AddNumberToObject(j,"requests",v->p->n_req);
        cJSON_AddNumberToObject(j,"can_sources",v->p->n_can);
        for(int i=0;i<SIG_STD_COUNT;i++) {
            strcpy(v->keys[i],sig_registry[i].key);v->stale[i]=sig_registry[i].stale_ms;
        }
        vp_engine_sink_t sink={0};sink.ctx=v;sink.send=send_cmd;sink.now_ms=now_ms;
        sink.set_signal=write_signal;sink.invalidate=invalidate;sink.set_speed_kmh=speed;
        sink.on_link=link_state;sink.veh_register=register_veh;sink.veh_clear=clear_veh;sink.reconnect=reconnect;
        v->e=vp_engine_create(v->p,&sink,NULL,&allocator);
        if(!v->e) cJSON_ReplaceItemInObject(j,"ok",cJSON_CreateBool(0));
    }
    char *output=emit(j); if(report)*report=output;else free(output);
    if(err!=VP_COMPILE_OK || !v->e) {sg_vehicle_close(v);return NULL;}
    return v;
}
void sg_vehicle_link(void *handle,int up,uint32_t now) {
    vehicle_t *v=handle;if(!v)return;v->now=now;v->pending=0;
    if(up)vp_engine_link_up(v->e);else vp_engine_link_down(v->e);
}
void sg_vehicle_rx(void *handle,const unsigned char *data,size_t len,uint32_t now) {
    vehicle_t *v=handle;if(!v || len>65536)return;v->now=now;vp_engine_on_rx(v->e,data,len);
}
unsigned sg_vehicle_run(void *handle,uint32_t now) {
    vehicle_t *v=handle;if(!v)return 100;v->now=now;return vp_engine_run(v->e);
}
int sg_vehicle_command(void *handle,char *out,size_t size) {
    vehicle_t *v=handle;if(!v || !v->pending || size<=strlen(v->command))return 0;
    strcpy(out,v->command);v->pending=0;return 1;
}
char *sg_vehicle_snapshot(void *handle) {
    vehicle_t *v=handle;if(!v)return NULL;
    vp_engine_stats_t stats;vp_engine_get_stats(v->e,&stats);
    cJSON *j=cJSON_CreateObject(),*values=cJSON_AddObjectToObject(j,"values");
    cJSON_AddNumberToObject(j,"link",stats.link);cJSON_AddBoolToObject(j,"reconnect",v->reconnect);
    cJSON_AddNumberToObject(j,"tx",stats.tx_cmds);cJSON_AddNumberToObject(j,"rx_ok",stats.rx_ok);
    for(int i=0;i<SIG_SLOT_COUNT;i++) {
        if(!v->keys[i][0])continue;
        bool fresh=v->valid[i] && (!v->stale[i] || (uint32_t)(v->now-v->stamp[i])<v->stale[i]);
        if((i<SIG_OBD_COUNT || i>=SIG_VEH_BASE) && stats.link!=SIG_LINK_DATA)fresh=false;
        if(fresh) {
            double value=v->val[i];if(i<SIG_STD_COUNT)value/=sig_registry[i].scale;
            cJSON_AddNumberToObject(values,v->keys[i],value);
        } else cJSON_AddNullToObject(values,v->keys[i]);
    }
    return emit(j);
}
