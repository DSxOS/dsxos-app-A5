from pyomo.environ import Var, Constraint, value
from pyomo.util.infeasible import log_infeasible_constraints
import sys
import io

def debug_model(m, filename="debug_output.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        # --------------------------------------------
        # 1. log_infeasible_constraints väljund failis
        # --------------------------------------------
        buffer = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buffer
        try:
            log_infeasible_constraints(m, log_expression=True)
        except Exception as e:
            buffer.write(f"VIGA log_infeasible_constraints() käivitamisel: {e}\n")
        finally:
            sys.stdout = old_stdout

        f.write("🔍 INFEASIBLE CONSTRAINTID\n")
        f.write(buffer.getvalue())

        # --------------------------------------------
        # 2. Kõik muutujad ja nende väärtused
        # --------------------------------------------
        f.write("\n📦 MUUTUJATE VÄÄRTUSED\n\n")
        for v in m.component_data_objects(ctype=Var, active=True):
            try:
                val_v = value(v)
                if val_v is None:
                    f.write(f"{v.name:40} = None\n")
                else:
                    f.write(f"{v.name:40} = {val_v:.4f}\n")
            except:
                f.write(f"{v.name:40} = [viga väärtuse lugemisel]\n")

        # --------------------------------------------
        # 3. Constraintide sisu ja väärtused
        # --------------------------------------------
        f.write("\n📏 CONSTRAINTIDE VÄÄRTUSED JA STAATUS\n\n")
        for c in m.component_data_objects(ctype=Constraint, active=True):
            try:
                body_val = value(c.body)
                lb_val = value(c.lower) if c.has_lb() else None
                ub_val = value(c.upper) if c.has_ub() else None

                if ((lb_val is not None and body_val < lb_val - 1e-4) or 
                    (ub_val is not None and body_val > ub_val + 1e-4)):
                    status = "❌ EI MAHU PIIRIDESSE"
                else:
                    status = "✅ OK"

                f.write(
                    f"{c.name:40} : body={body_val:.3f}, lower={lb_val}, upper={ub_val} --> {status}\n"
                )
            except:
                f.write(f"{c.name:40} = [viga constrainti väärtuse arvutamisel]\n")

    print(f"📄 Debug info salvestatud faili: {filename}")
