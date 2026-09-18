"""旅行规划API路由"""

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool
from ...models.schemas import (
    TripRequest,
    TripPlanResponse,
    ErrorResponse,
    PlanCandidateResponse,
    PlanCandidateData,
    PlanConfirmRequest,
)
from ...agents.trip_planner_agent import get_trip_planner_agent

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

        # 获取Agent实例
        print("🔄 获取多智能体系统实例...")
        agent = await run_in_threadpool(get_trip_planner_agent)

        # 生成旅行计划
        print("🚀 开始生成旅行计划...")
        trip_plan = await run_in_threadpool(agent.plan_trip, request)

        print("✅ 旅行计划生成成功,准备返回响应\n")

        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功",
            data=trip_plan
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
            user_feedback=request.user_feedback
        )

        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功（已融入用户确认要求）",
            data=trip_plan
        )
    except Exception as e:
        print(f"❌ HITL 确认恢复旅行计划失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成旅行计划失败: {str(e)}")



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
