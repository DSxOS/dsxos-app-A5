from pyomo.environ import Var, Constraint, value
from pyomo.util.infeasible import log_infeasible_constraints
import sys
import io
import logging

def debug_model(m, filename="debug_output.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        # --------------------------------------------
        # 1. Log infeasible constraints to output file
        # --------------------------------------------
        log_stream = io.StringIO()

        # Temporary logger configuration
        logger = logging.getLogger("pyomo.util.infeasible")
        old_handlers = logger.handlers[:]
        logger.handlers = []  # temporarily remove existing handlers
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            log_infeasible_constraints(m)
        except Exception as e:
            log_stream.write(f"❗ Error while running log_infeasible_constraints(): {e}\n")
        finally:
            logger.handlers = old_handlers  # restore original logger handlers

        f.write("🔍 INFEASIBLE CONSTRAINTS\n")
        f.write(log_stream.getvalue())

        # --------------------------------------------
        # 2. All variable values
        # --------------------------------------------
        f.write("\n📦 VARIABLE VALUES\n\n")
        for v in m.component_data_objects(ctype=Var, active=True):
            try:
                val_v = value(v)
                if val_v is None:
                    f.write(f"{v.name:40} = None\n")
                else:
                    f.write(f"{v.name:40} = {val_v:.4f}\n")
            except:
                f.write(f"{v.name:40} = [error reading value]\n")

        # --------------------------------------------
        # 3. Constraint expressions and evaluation
        # --------------------------------------------
        f.write("\n📏 CONSTRAINT EVALUATION\n\n")
        for c in m.component_data_objects(ctype=Constraint, active=True):
            try:
                body_val = value(c.body)
                lb_val = value(c.lower) if c.has_lb() else None
                ub_val = value(c.upper) if c.has_ub() else None

                if ((lb_val is not None and body_val < lb_val - 1e-4) or 
                    (ub_val is not None and body_val > ub_val + 1e-4)):
                    status = "❌ OUT OF BOUNDS"
                else:
                    status = "✅ OK"

                f.write(
                    f"{c.name:40} : body={body_val:.3f}, lower={lb_val}, upper={ub_val} --> {status}\n"
                )
            except:
                f.write(f"{c.name:40} = [error evaluating constraint]\n")

    print(f"📄 Debug information saved to: {filename}")
