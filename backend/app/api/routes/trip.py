import json
import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from ...models.schemas import (
    TripRequest,
    TripPlanResponse,
    ErrorResponse,
    PlanCandidateResponse,
    PlanCandidateData,
    PlanConfirmRequest,
    TripStateResponse,
    TripStateData,
    TripHistoryResponse,
    CheckpointSnapshot,
    ChatModifyRequest,
    ChatModifyResponse,
    NaturalLanguageParseRequest,
    NaturalLanguageParseResponse,
)
from ...agents.trip_planner_agent import get_trip_planner_agent, parse_natural_language_trip
from ...agents.chat_modify_agent import get_chat_modify_agent

router = APIRouter(prefix="/trip", tags=["旅行规划"])



@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划",
    description="根据用户输入的旅行需求,生成详细的旅行计划"
)
async def plan_trip(request: TripRequest):
    """
    生成旅行计划

    Args:
        request: 旅行请求参数

    Returns:
        旅行计划响应
    """
    try:
        print(f"\n{'='*60}")
        print(f"📥 收到旅行规划请求:")
        print(f"   城市: {request.city}")
        print(f"   日期: {request.start_date} - {request.end_date}")
        print(f"   天数: {request.travel_days}")
        print(f"{'='*60}\n")

        tid = request.thread_id or f"trip_{uuid.uuid4().hex[:12]}"
        request.thread_id = tid

        # 获取Agent实例
        print("🔄 获取多智能体系统实例...")
        agent = await run_in_threadpool(get_trip_planner_agent)

        # 生成旅行计划
        print(f"🚀 开始生成旅行计划 (thread_id={tid})...")
        import inspect
        sig = inspect.signature(agent.plan_trip)
        if "thread_id" in sig.parameters or any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
            trip_plan = await run_in_threadpool(agent.plan_trip, request, thread_id=tid)
        else:
            trip_plan = await run_in_threadpool(agent.plan_trip, request)

        print("✅ 旅行计划生成成功,准备返回响应\n")

        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功",
            data=trip_plan,
            thread_id=tid
        )

    except Exception as e:
        print(f"❌ 生成旅行计划失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"生成旅行计划失败: {str(e)}"
        )


@router.post(
    "/plan/stream",
    summary="流式生成旅行计划 (SSE)",
    description="利用 LangGraph astream 逐个推送智能体专家节点的执行状态与最终旅行计划"
)
async def plan_trip_stream(request: TripRequest):
    """流式返回旅行规划进展及最终计划 (SSE)"""
    try:
        tid = request.thread_id or f"trip_{uuid.uuid4().hex[:12]}"
        request.thread_id = tid
        agent = await run_in_threadpool(get_trip_planner_agent)

        async def sse_event_stream():
            try:
                yield ": ping\n\n"
                async for event_data in agent.astream_plan_trip(request, thread_id=tid):
                    event_name = event_data.get("event", "message")
                    payload = json.dumps(event_data, ensure_ascii=False)
                    yield f"event: {event_name}\ndata: {payload}\n\n"
            except Exception as exc:
                err_payload = json.dumps({"event": "error", "message": str(exc), "thread_id": tid}, ensure_ascii=False)
                yield f"event: error\ndata: {err_payload}\n\n"

        return StreamingResponse(
            sse_event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    except Exception as e:
        print(f"❌ 流式生成旅行计划启动失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"流式旅行规划失败: {str(e)}")


@router.post(
    "/plan/prepare",

    response_model=PlanCandidateResponse,
    summary="准备旅行规划（HITL 阶段一）",
    description="执行景点、天气、酒店并行查询，在规划生成前挂起，返回候选数据供用户确认"
)
async def prepare_trip_plan(request: TripRequest):
    """准备旅行规划：并行收集候选数据并在规划前挂起"""
    try:
        print(f"\n{'='*60}")
        print(f"📥 收到 HITL 阶段一请求 (候选收集):")
        print(f"   城市: {request.city}")
        print(f"   日期: {request.start_date} - {request.end_date}")
        print(f"{'='*60}\n")

        agent = await run_in_threadpool(get_trip_planner_agent)
        candidate_result = await run_in_threadpool(agent.prepare_trip_plan, request)

        return PlanCandidateResponse(
            success=True,
            message="候选数据获取成功，已在规划生成前挂起，等待用户确认",
            data=PlanCandidateData(**candidate_result)
        )
    except Exception as e:
        print(f"❌ HITL 准备旅行计划失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"准备旅行计划失败: {str(e)}")


@router.post(
    "/plan/confirm",
    response_model=TripPlanResponse,
    summary="确认并生成旅行计划（HITL 阶段二）",
    description="接收用户挑选确认的景点、酒店与修改意见，恢复 LangGraph 图执行生成完整行程"
)
async def confirm_trip_plan(request: PlanConfirmRequest):
    """确认候选并恢复执行生成旅行计划"""
    try:
        print(f"\n{'='*60}")
        print(f"📥 收到 HITL 阶段二请求 (用户确认与恢复执行):")
        print(f"   thread_id: {request.thread_id}")
        print(f"   选定景点: {request.selected_attractions}")
        print(f"   选定酒店: {request.selected_hotel}")
        print(f"   用户反馈: {request.user_feedback}")
        print(f"{'='*60}\n")

        agent = await run_in_threadpool(get_trip_planner_agent)
        trip_plan = await run_in_threadpool(
            agent.resume_trip_plan,
            thread_id=request.thread_id,
            selected_attractions=request.selected_attractions,
            selected_hotel=request.selected_hotel,
            user_feedback=request.user_feedback,
            start_date=request.start_date,
            end_date=request.end_date,
        )

        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功（已融入用户确认要求）",
            data=trip_plan,
            thread_id=request.thread_id
        )
    except Exception as e:
        print(f"❌ HITL 确认恢复旅行计划失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成旅行计划失败: {str(e)}")


@router.get(
    "/plan/state/{thread_id}",
    response_model=TripStateResponse,
    summary="查询规划会话状态",
    description="查询指定 thread_id 的当前图执行状态、待执行节点与中间数据"
)
async def get_plan_state(thread_id: str):
    """查询指定会话状态"""
    try:
        agent = await run_in_threadpool(get_trip_planner_agent)
        state_data = await run_in_threadpool(agent.get_trip_state, thread_id)
        if not state_data:
            raise HTTPException(status_code=404, detail=f"未找到会话 {thread_id} 的状态快照")
        return TripStateResponse(
            success=True,
            message="获取会话状态成功",
            data=TripStateData(**state_data)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询会话状态失败: {str(e)}")


@router.get(
    "/plan/history/{thread_id}",
    response_model=TripHistoryResponse,
    summary="查询规划会话历史快照",
    description="查询指定 thread_id 的所有检查点时间线历史，支持执行追踪与历史回溯"
)
async def get_plan_history(thread_id: str):
    """查询指定会话检查点演进历史"""
    try:
        agent = await run_in_threadpool(get_trip_planner_agent)
        history = await run_in_threadpool(agent.get_trip_history, thread_id)
        if not history:
            raise HTTPException(status_code=404, detail=f"未找到会话 {thread_id} 的检查点历史")
        snapshots = [CheckpointSnapshot(**item) for item in history]
        return TripHistoryResponse(
            success=True,
            message="获取会话历史快照成功",
            thread_id=thread_id,
            total_checkpoints=len(snapshots),
            history=snapshots
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询会话历史失败: {str(e)}")


@router.post(
    "/chat/modify",
    response_model=ChatModifyResponse,
    summary="对话式修改旅行计划 (LangGraph chat_modify 子图)",
    description="通过自然语言与 Agent 对话，调整行程中的景点、酒店、餐饮或预算，并联动更新计划"
)
async def chat_modify_plan(request: ChatModifyRequest):
    """通过自然语言修改已生成的旅行计划"""
    try:
        print(f"\n{'='*60}")
        print(f"💬 收到对话式修改指令:")
        print(f"   会话ID: {request.thread_id}")
        print(f"   用户指令: {request.message}")
        print(f"{'='*60}\n")

        modifier = await run_in_threadpool(get_chat_modify_agent)
        result_data = await run_in_threadpool(modifier.modify_plan, request)

        return ChatModifyResponse(
            success=True,
            message="行程修改处理成功",
            data=result_data,
        )
    except Exception as e:
        print(f"❌ 对话修改行程失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"行程修改失败: {str(e)}")


@router.post(
    "/chat/parse",
    response_model=NaturalLanguageParseResponse,
    summary="自然语言旅行意图提取",
    description="将用户在对话框中输入的自然语言（如：'我想去北京玩3天，预算3000'）自动转换为标准旅行请求对象"
)
async def chat_parse_intent(request: NaturalLanguageParseRequest):
    """将自然语言描述提取为 TripRequest 参数"""
    try:
        trip_req = await run_in_threadpool(parse_natural_language_trip, request.text)
        return NaturalLanguageParseResponse(
            success=True,
            message="提取成功",
            data=trip_req,
        )
    except Exception as e:
        print(f"❌ 自然语言意图提取失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"意图提取失败: {str(e)}")


@router.get(
    "/health",

    summary="健康检查",
    description="检查旅行规划服务是否正常"
)
async def health_check():
    """健康检查"""
    try:
        # 检查Agent是否可用
        agent = await run_in_threadpool(get_trip_planner_agent)
        
        return {
            "status": "healthy",
            "service": "trip-planner",
            "agent_name": "多智能体旅行规划系统",
            "agents": list(agent.agent_names)
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"服务不可用: {str(e)}"
        )
